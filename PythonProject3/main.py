import hashlib
import json
import time
import requests
from datetime import datetime

# 🔧 替換成你的 SheetDB API
CHAIN_SHEETDB_API = "https://sheetdb.io/api/v1/jlrl9dhelxbt0"        # 區塊鏈鏈資料
TRANSACTIONS_SHEETDB_API = "https://sheetdb.io/api/v1/k3lieijz7zedc" # 交易紀錄

# 碳排放係數
MACHINE_EMISSION = {
    "高空作業機": 2.5,
    "除草車": 1.8,
    "大分類機": 3.0,
    "小分類機": 2.0
}

class Blockchain:
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.load_chain_from_sheet()

    @property
    def last_block(self):
        return self.chain[-1] if self.chain else None

    @staticmethod
    def hash(block):
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def new_transaction(self, date, machine, fertilizer, amount, emission):
        self.current_transactions.append({
            "date": date,
            "machine": machine,
            "fertilizer": fertilizer,
            "amount": amount,
            "emission": emission
        })
        return self.last_block["index"] + 1 if self.last_block else 1

    def new_block(self, proof, previous_hash=None):
        block = {
            "index": len(self.chain) + 1,
            "timestamp": time.time(),
            "transactions": self.current_transactions,
            "proof": proof,
            "previous_hash": previous_hash or self.hash(self.chain[-1]),
        }
        self.chain.append(block)

        # 🟡 修正：在這裡傳入 block["index"]，確保 block_index 對應正確
        self.save_new_transactions_to_sheet(block["transactions"], block_index=block["index"])

        self.current_transactions = []
        self.save_chain_to_sheet()
        return block

    def save_chain_to_sheet(self):
        requests.delete(CHAIN_SHEETDB_API)
        data = {"data": [{"chain": json.dumps(self.chain, ensure_ascii=False)}]}
        headers = {"Content-Type": "application/json; charset=utf-8"}
        requests.post(CHAIN_SHEETDB_API, json=data, headers=headers)

    # 🟡 修正：新增 block_index 參數，避免使用 last_block["index"]
    def save_new_transactions_to_sheet(self, new_transactions, block_index):
        if not new_transactions:
            return
        data = {"data": []}
        for tx in new_transactions:
            data["data"].append({
                "block_index": block_index,  # ✅ 正確的區塊編號
                "date": tx["date"],
                "machine": tx["machine"],
                "fertilizer": tx["fertilizer"],
                "amount": tx["amount"],
                "emission": tx["emission"]
            })
        headers = {"Content-Type": "application/json; charset=utf-8"}
        requests.post(TRANSACTIONS_SHEETDB_API, json=data, headers=headers)

    def load_chain_from_sheet(self):
        try:
            res = requests.get(CHAIN_SHEETDB_API).json()
        except Exception as e:
            print("⚠ 無法取得鏈資料:", e)
            res = []

        if isinstance(res, list) and len(res) > 0 and "chain" in res[0]:
            try:
                self.chain = json.loads(res[0]["chain"])
            except json.JSONDecodeError:
                print("⚠ 鏈資料無法解析，建立創世區塊")
                self.chain = []
        else:
            self.chain = []

        if not self.chain:
            genesis_block = {
                "index": 1,
                "timestamp": time.time(),
                "transactions": [],
                "proof": 100,
                "previous_hash": "1"
            }
            self.chain = [genesis_block]
            self.save_chain_to_sheet()


# 🟡 修正：移除「去重邏輯」，並按 block_index 排序
def get_all_transactions(blockchain):
    all_transactions = []
    for block in blockchain.chain:
        for tx in block["transactions"]:
            all_transactions.append({
                "block_index": block["index"],
                "date": tx["date"],
                "machine": tx["machine"],
                "fertilizer": tx["fertilizer"],
                "amount": tx["amount"],
                "emission": tx["emission"]
            })
    # ✅ 按照區塊編號排序，避免順序亂跳
    all_transactions.sort(key=lambda x: x["block_index"])
    return all_transactions


# ✅ 自動記錄今天日期
def input_transaction():
    print("請輸入交易資料：")
    date = datetime.now().strftime("%Y-%m-%d")   # ⬅ 自動抓取今天日期
    print(f"📅 系統已自動記錄日期：{date}")

    print("機器類型選擇：" + ", ".join(MACHINE_EMISSION.keys()))
    machine = input("機器: ").strip()
    fertilizer = input("肥料: ").strip()
    while True:
        try:
            amount = float(input("使用量(數字): ").strip())
            break
        except ValueError:
            print("請輸入有效數字")
    return date, machine, fertilizer, amount


def main():
    blockchain = Blockchain()
    print(f"目前鏈長度：{len(blockchain.chain)}")

    while True:
        cmd = input("\n請輸入指令 [add: 新增交易並挖礦, show: 顯示交易, exit: 離開]: ").strip().lower()

        if cmd == "add":
            date, machine, fertilizer, amount = input_transaction()
            emission_factor = MACHINE_EMISSION.get(machine, 1.0)
            emission = amount * emission_factor
            idx = blockchain.new_transaction(date, machine, fertilizer, amount, emission)
            block = blockchain.new_block(proof=idx)
            print(f"✅ 交易已加入區塊 {block['index']} 並挖出新區塊")

        elif cmd == "show":
            print("\n===== 交易紀錄 =====")
            all_tx = get_all_transactions(blockchain)
            if not all_tx:
                print("目前沒有交易紀錄")
            else:
                for tx in all_tx:
                    print(f"區塊 {tx['block_index']}: 日期 {tx['date']}, 機器 {tx['machine']}, "
                          f"肥料 {tx['fertilizer']}, 使用量 {tx['amount']}, 排放 {tx['emission']}")

            total_emission = sum(tx["emission"] for tx in all_tx)
            print(f"\n🌱 累計碳排放量: {total_emission:.2f} kg CO₂")

        elif cmd == "exit":
            print("程式結束")
            break

        else:
            print("無效指令，請重新輸入")


if __name__ == "__main__":
    main()

