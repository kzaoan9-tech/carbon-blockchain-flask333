import hashlib
import json
import time
import requests
import copy
import uuid
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for


# ==================== 1. 全域配置 ====================
BASE_SHEETDB_URL = "https://sheetdb.io/api/v1/pzxbqqv7af83i"
KNOWN_NODE_IDS = ["node1", "node2", "node3"]


def chains_sheet_url(node_id):
   return f"{BASE_SHEETDB_URL}?sheet={node_id}_chains"




def tx_pool_url():
   return f"{BASE_SHEETDB_URL}?sheet=transactions"


# 機器碳排放係數對照表 (Emission Factors)
MACHINE_FACTORS = {
   "除草機": 1.50,
   "大小分類機": 0.85,
   "堆高機": 2.10,
   "搬運車": 1.95
}
# 肥料碳排放係數對照表 (單位: kg CO2e / 公斤)
FERTILIZER_FACTORS = {
   "尿素": 2.50,         # 假設值
   "複合肥料": 1.80,      # 假設值
   "有機質肥料": 0.50     # 假設值
}
# ==================== 2. 工具函數 ====================
FIXED_GENESIS = {
   "index": 1,
   "timestamp": "t1700000000",
   "transactions": [],
   "proof": 100,
   "previous_hash": "0"
}




def format_ts(ts):
   clean_ts = str(ts).replace("t", "").strip()
   if "." in clean_ts: clean_ts = clean_ts.split(".")[0]
   return "t" + clean_ts




def format_val(val):
   try:
       if val == "" or val is None: return "0.00"
       return "{:.2f}".format(float(val))
   except:
       return "0.00"




def normalize_block(block):
   b = copy.deepcopy(block)
   try:
       # 確保型態強制轉換，避免 Google Sheets 的自動轉型破壞雜湊
       b["index"] = int(b["index"])
       b["timestamp"] = format_ts(b["timestamp"])
       b["proof"] = int(b["proof"])
       b["previous_hash"] = str(b["previous_hash"])
       # ... (其餘邏輯)
   except Exception as e:
       print(f"❌ 數據標準化失敗: {e} | 原始資料: {block}")
   return b




def calc_hash(block):
   std = normalize_block(block)
   target = {
       "index": std["index"], "timestamp": std["timestamp"],
       "transactions": std["transactions"], "proof": std["proof"],
       "previous_hash": std["previous_hash"]
   }
   raw_str = json.dumps(target, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
   return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()




# ==================== 3. 區塊鏈核心 ====================
class BlockchainNode:
   def __init__(self, node_id):
       self.lock = threading.Lock()  # 加入鎖
       self.node_id = node_id
       self.chain = []


       # 這裡加上顯示，讓你知道現在在初始化哪一個
       print(f"\n[系統] 節點 {self.node_id} 正在啟動中...")
       print("-" * 40)


       self.load_local_chain()
       self.sync_and_consensus()


       if not self.chain:
           print(f"   [!] 雲端查無資料，正在為 {self.node_id} 生成創世區塊...")
           self.init_genesis()


       print(f"✅ 節點 {self.node_id} 就緒。鏈長度: {len(self.chain)}")
       print("-" * 40)


   def load_local_chain(self):
       try:
           r = requests.get(chains_sheet_url(self.node_id), timeout=15)
           data = r.json()
           rows = data.get("rows", []) if isinstance(data, dict) else data
           new_chain = []
           for row in rows:
               raw_b = {
                   "index": row.get("index"), "timestamp": row.get("timestamp"),
                   "transactions": json.loads(row.get("transactions", "[]")),
                   "proof": row.get("proof"), "previous_hash": row.get("previous_hash"),
                   "hash": row.get("hash")
               }
               std_b = normalize_block(raw_b)
               std_b["hash"] = str(row.get("hash"))
               new_chain.append(std_b)
           new_chain.sort(key=lambda b: b["index"])
           self.chain = new_chain
       except:
           self.chain = []


   def validate_chain(self, chain):
       if not chain: return False
       if str(chain[0]["timestamp"]) != str(format_ts(FIXED_GENESIS["timestamp"])): return False
       for i in range(1, len(chain)):
           if str(chain[i]["previous_hash"]) != str(chain[i - 1]["hash"]): return False
           if calc_hash(chain[i]) != chain[i]["hash"]: return False
       return True


   def sync_and_consensus(self):
       print(f"🔍 {self.node_id} 正在掃描全網共識狀態...")
       best_chain = self.chain
       found_better = False


       for nid in KNOWN_NODE_IDS:
           if nid == self.node_id: continue


           try:
               print(f"   📡 正在請求節點 {nid} 的數據...", end=" ")
               r = requests.get(chains_sheet_url(nid), timeout=5)
               if r.status_code != 200:
                   print("📴 離線")
                   continue


               ext_data = r.json()
               ext_rows = ext_data.get("rows", []) if isinstance(ext_data, dict) else ext_data


               # --- [加回功能]：嚴格還原外部鏈條格式 ---
               ext_chain = []
               for er in ext_rows:
                   b = normalize_block({
                       "index": er["index"],
                       "timestamp": er["timestamp"],
                       "transactions": json.loads(er["transactions"] or "[]"),
                       "proof": er["proof"],
                       "previous_hash": er["previous_hash"]
                   })
                   b["hash"] = er["hash"]
                   ext_chain.append(b)
               ext_chain.sort(key=lambda x: x["index"])


               if not ext_chain:
                   print("🈳 空鏈")
                   continue


               # --- [加回功能]：分岔偵測與完整性驗證 ---
               if not self.validate_chain(ext_chain):
                   print(f"🚫 [拒絕] 節點 {nid} 資料驗證失敗。")
                   continue


               # 偵測分岔點 (Debug 用)
               min_len = min(len(self.chain), len(ext_chain))
               for i in range(min_len):
                   if self.chain[i]["hash"] != ext_chain[i]["hash"]:
                       print(f"⚠️ 在區塊 #{i + 1} 發現與 {nid} 的分岔")
                       break


               # 最長鏈採納
               if len(ext_chain) > len(best_chain):
                   print(f"🚀 [勝出] 高度 {len(ext_chain)}!")
                   best_chain = ext_chain
                   found_better = True
               else:
                   print("✅ 已同步或高度不足")


           except Exception as e:
               print(f"📴 連線錯誤: {e}")


       if found_better:
           print(f"🔄 正在將 {self.node_id} 更新為最強合法鏈...")
           self.chain = copy.deepcopy(best_chain)
           self.rebuild_cloud_chain()


   def rebuild_cloud_chain(self):
       try:
           requests.delete(f"{BASE_SHEETDB_URL}/all?sheet={self.node_id}_chains", timeout=15)
           for block in self.chain:
               payload = {
                   "index": block["index"], "timestamp": block["timestamp"],
                   "transactions": json.dumps(block["transactions"], ensure_ascii=False),
                   "proof": block["proof"], "previous_hash": block["previous_hash"],
                   "hash": block["hash"]
               }
               requests.post(chains_sheet_url(self.node_id), json={"data": [payload]})
       except:
           pass


   def init_genesis(self):
       g = normalize_block(FIXED_GENESIS)
       g["hash"] = calc_hash(g)
       self.chain = [g]
       self.rebuild_cloud_chain()


   def add_transaction_and_mine(self, machine, hours, fertilizer_type, fertilizer_kg, amount):


       """核心：根據機器類型計算不同碳排放並打包區塊 (已修正縮排與鎖定範圍)"""
       with self.lock:  # 鎖定開始：確保同一時間只有一個請求在進行同步與挖礦
           print(f"\n⚒️ {self.node_id} 正在啟動打包程序...")


           # 1. 挖礦前先執行全網共識同步，確保基礎是最新且正確的
           self.sync_and_consensus()


           # 取得最新區塊索引
           next_idx = self.chain[-1]["index"] + 1


           # --- 計算碳排放 (CO2e) ---
           # 1. 機器排放
           m_factor = MACHINE_FACTORS.get(machine, 0.00)
           m_emission = float(hours) * m_factor


           # 2. 肥料排放
           f_factor = FERTILIZER_FACTORS.get(fertilizer_type, 0.00)
           f_emission = float(fertilizer_kg) * f_factor


           # 3. 總計
           total_co2e = format_val(m_emission + f_emission)


           # 建立交易資料
           tx = {
               "tx_id": str(uuid.uuid4())[:8],
               "machine": str(machine),
               "hours": format_val(hours),
               "fertilizer_type": str(fertilizer_type),
               "fertilizer_kg": format_val(fertilizer_kg),
               "amount": format_val(amount),
               "emission_co2e": total_co2e,  # 改名為 co2e
               "status": "packed",
               "block_index": next_idx,
               "node_id": self.node_id,
               "date": datetime.now().strftime("%Y-%m-%d")
           }


           # 2. 存入交易總池 (transactions 表)
           try:
               requests.post(tx_pool_url(), json={"data": [tx]}, timeout=10)
               print(f"   📝 交易已同步至總池 (ID: {tx['tx_id']})")
           except Exception as e:
               print(f"   ⚠️ 交易池同步失敗: {e}，但將繼續打包區塊...")


           # 3. 封裝區塊
           new_block = normalize_block({
               "index": next_idx,
               "timestamp": format_ts(time.time()),
               "transactions": [tx],
               "proof": 100,
               "previous_hash": self.chain[-1]["hash"]
           })
           new_block["hash"] = calc_hash(new_block)


           # 4. 更新本地記憶體中的鏈
           self.chain.append(new_block)


           # 5. 將新區塊廣播/上傳至該節點的雲端分頁
           try:
               payload = {
                   "index": new_block["index"],
                   "timestamp": new_block["timestamp"],
                   "transactions": json.dumps(new_block["transactions"], ensure_ascii=False),
                   "proof": new_block["proof"],
                   "previous_hash": new_block["previous_hash"],
                   "hash": new_block["hash"]
               }
               requests.post(chains_sheet_url(self.node_id), json={"data": [payload]}, timeout=15)
               print(f"🎉 成功！總排放量: {total_co2e} kg CO2e")
           except Exception as e:
               print(f"❌ 雲端區塊廣播失敗: {e}")


       # 鎖定在此結束，下一個請求才能進入




# ==================== 4. Flask 路由 ====================
app = Flask(__name__)
nodes = {
   "node1": BlockchainNode("node1"),
   "node2": BlockchainNode("node2"),
   "node3": BlockchainNode("node3")
}


@app.route('/')
def home():
   return redirect('/node1')




@app.route('/<target_node>')
def node_index(target_node):
   if target_node not in nodes: return "Error", 404


   # 【新增這行】每次進入頁面都自動同步一次
   nodes[target_node].sync_and_consensus()


   current_node = nodes[target_node]
   return render_template('index.html',
                          chain=current_node.chain[::-1],
                          node_id=current_node.node_id)




@app.route('/<target_node>/add', methods=['POST'])
def add_record(target_node):
   if target_node in nodes:
       m = request.form.get('machine')
       h = request.form.get('hours')
       ft = request.form.get('fertilizer_type')  # 新增
       fk = request.form.get('fertilizer_kg')  # 新增
       a = request.form.get('amount')


       if m and h and ft and fk and a:
           nodes[target_node].add_transaction_and_mine(m, h, ft, fk, a)
   return redirect(f'/{target_node}')




@app.route('/<target_node>/sync')
def sync_blockchain(target_node):
   if target_node in nodes:
       # 這裡必須呼叫字典裡的實例
       nodes[target_node].sync_and_consensus()
       print(f"🔄 節點 {target_node} 手動同步完成")
   return redirect(f'/{target_node}')




if __name__ == "__main__":
   # 這邊會等上面的 nodes 初始化完才執行
   print("\n" + "=" * 50)
   print("🚀 伺服器已就緒，請開啟瀏覽器訪問。")
   print("=" * 50 + "\n")


   import os


   port = int(os.environ.get("PORT", 5000))
   app.run(host='0.0.0.0', port=port)


這是main.py








<!DOCTYPE html>
<html lang="zh-Hant">
<head>
   <meta charset="UTF-8">
   <meta name="viewport" content="width=device-width, initial-scale=1.0">
   <title>綠色區塊鏈 - 節點控制台</title>
   <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
   <style>
       body { background-color: #f8f9fa; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
       .navbar { background-color: #198754 !important; }
       .card { border: none; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-radius: 12px; }
       .block-card { border-left: 5px solid #198754; margin-bottom: 15px; transition: transform 0.2s; }
       .block-card:hover { transform: scale(1.01); }
       .hash-text { font-family: 'Courier New', Courier, monospace; font-size: 0.85rem; color: #6c757d; word-break: break-all; }
       .node-badge { font-size: 1rem; padding: 8px 16px; border-radius: 50px; }
       .emission-val { color: #d63384; font-weight: bold; }
       .section-title { font-size: 0.9rem; color: #198754; font-weight: bold; margin-top: 10px; border-bottom: 1px solid #eee; }
       .small-unit { font-size: 0.7rem; color: #6c757d; }
   </style>
</head>
<body>


<nav class="navbar navbar-dark shadow-sm">
   <div class="container">
       <a class="navbar-brand fw-bold" href="/">🌿 GreenChain 碳足跡監測系統</a>
       <span class="badge bg-light text-dark node-badge">當前節點：{{ node_id }}</span>
   </div>
</nav>


<div class="container mt-4">
   <div class="row">
       <div class="col-md-4">
           <div class="card p-4 mb-4">
               <h5 class="fw-bold mb-3">📦 打包新數據區塊</h5>
               <form action="/{{ node_id }}/add" method="POST">


                   <div class="section-title mb-2">🚜 機器運作數據</div>
                   <div class="mb-3">
                       <select class="form-select" name="machine" required>
                           <option value="" selected disabled>請選擇機器...</option>
                           <option value="除草機">除草機</option>
                           <option value="大小分類機">大小分類機</option>
                           <option value="堆高機">堆高機</option>
                           <option value="搬運車">搬運車</option>
                       </select>
                   </div>
                   <div class="mb-3">
                       <div class="input-group">
                           <input type="number" step="0.1" class="form-control" name="hours" placeholder="運作時數" required>
                           <span class="input-group-text">Hours</span>
                       </div>
                   </div>


                   <div class="section-title mb-2">🌱 肥料施用數據</div>
                   <div class="mb-3">
                       <select class="form-select" name="fertilizer_type" required>
                           <option value="" selected disabled>請選擇肥料...</option>
                           <option value="尿素">尿素</option>
                           <option value="複合肥料">複合肥料</option>
                           <option value="有機質肥料">有機質肥料</option>
                           <option value="無">無</option>
                       </select>
                   </div>
                   <div class="mb-3">
                       <div class="input-group">
                           <input type="number" step="0.1" class="form-control" name="fertilizer_kg" placeholder="肥料重量" required>
                           <span class="input-group-text">kg</span>
                       </div>
                   </div>


                   <div class="section-title mb-2">💰 經濟成本</div>
                   <div class="mb-3">
                       <div class="input-group">
                           <span class="input-group-text">$</span>
                           <input type="number" class="form-control" name="amount" placeholder="維護金額" required>
                       </div>
                   </div>


                   <button type="submit" class="btn btn-success w-100 fw-bold shadow-sm mt-2">確認並計算 CO2e 打包</button>
                   <p class="text-muted mt-3 text-center" style="font-size: 0.75rem;">
                       💡 系統將自動根據 <b>設定的係數</b><br>計算機器與肥料之綜合排放量
                   </p>
               </form>
           </div>


           <div class="card p-3">
               <h6 class="fw-bold text-success">🌐 網路狀態</h6>
               <div class="d-flex justify-content-between align-items-center mb-2">
                   <span class="small">全網共識狀態</span>
                   <span class="badge bg-success">已同步</span>
               </div>
               <a href="/{{ node_id }}/sync" class="btn btn-outline-primary btn-sm w-100">強制手動同步全網數據</a>
           </div>
       </div>


       <div class="col-md-8">
           <h5 class="fw-bold mb-3">🔗 分散式帳本 (kg CO2e 追蹤)</h5>


           {% for block in chain %}
           <div class="card block-card p-3">
               <div class="d-flex justify-content-between align-items-start">
                   <div>
                       <span class="badge bg-dark mb-2">Block #{{ block.index }}</span>
                       <span class="text-muted ms-2 small">{{ block.timestamp }}</span>
                   </div>
                   {% if block.index == 1 %}
                   <span class="badge bg-warning text-dark">Genesis Block</span>
                   {% endif %}
               </div>


               {% if block.transactions %}
                   {% for tx in block.transactions %}
                   <div class="bg-light p-3 rounded my-2 border">
                       <div class="row mb-2">
                           <div class="col-6"><strong>🚜 設備:</strong> {{ tx.machine }}</div>
                           <div class="col-6 text-end"><strong>🌱 肥料:</strong> {{ tx.fertilizer_type }}</div>
                       </div>
                       <hr class="my-1">
                       <div class="row small py-2 text-center">
                           <div class="col-3 border-end">時數<br><strong>{{ tx.hours }}</strong></div>
                           <div class="col-3 border-end">重量<br><strong>{{ tx.fertilizer_kg }} kg</strong></div>
                           <div class="col-3 border-end">金額<br><strong>${{ tx.amount }}</strong></div>
                           <div class="col-3">排放量<br><span class="emission-val">{{ tx.emission_co2e }}</span> <span class="small-unit">kg CO2e</span></div>
                       </div>
                       <div class="text-end text-muted" style="font-size: 0.65rem; letter-spacing: 1px;">
                           TXID: {{ tx.tx_id }}
                       </div>
                   </div>
                   {% endfor %}
               {% else %}
                   <div class="text-center text-muted py-4">
                       <p class="mb-0">-- 創世區塊：網路啟動 --</p>
                   </div>
               {% endif %}


               <div class="mt-2 bg-white p-2 rounded border-start border-3 border-secondary">
                   <div class="small fw-bold text-secondary">Current Hash:</div>
                   <div class="hash-text">{{ block.hash }}</div>
                   <div class="small fw-bold text-secondary mt-1">Previous Hash:</div>
                   <div class="hash-text">{{ block.previous_hash }}</div>
               </div>
           </div>
           {% endfor %}
       </div>
   </div>
</div>


<footer class="text-center py-5 text-muted">
   <hr class="container mb-4">
   <small>© 2026 GreenChain 區塊鏈技術展示 - 分布式帳本</small><br>
