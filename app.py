from flask import Flask, render_template, request, redirect, url_for
import hashlib
import json
import time
import requests
from datetime import datetime

app = Flask(__name__)

# 🔧 你的 SheetDB API
CHAIN_SHEETDB_API = "https://sheetdb.io/api/v1/jlrl9dhelxbt0"
TRANSACTIONS_SHEETDB_API = "https://sheetdb.io/api/v1/k3lieijz7zedc"

# 碳排放係數
MACHINE_EMISSION = {
    "高空作業機": 2.5,
    "除草車": 1.8,
    "大分類機": 3.0,
    "小分類機": 2.0
}


# 區塊鏈核心類別
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

        # ✅ 使用新區塊的 index，避免 block_index 亂跳
        self.save_new_transactions_to_sheet(block["transactions"], block_index=block["index"])

        self.current_transactions = []
        self.save_chain_to_sheet()
        return block

    def save_chain_to_sheet(self):
        requests.delete(CHAIN_SHEETDB_API)
        data = {"data": [{"chain": json.dumps(self.chain, ensure_ascii=False)}]}
        headers = {"Content-Type": "application/json; charset=utf-8"}
        requests.post(CHAIN_SHEETDB_API, json=data, headers=headers)

    def save_new_transactions_to_sheet(self, new_transactions, block_index):
        if not new_transactions:
            return
        data = {"data": []}
        for tx in new_transactions:
            data["data"].append({
                "block_index": block_index,
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


# 建立區塊鏈實例
blockchain = Blockchain()


# 取得所有交易（按區塊排序）
def get_all_transactions():
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
    all_transactions.sort(key=lambda x: x["block_index"])
    return all_transactions


# 📄 首頁：顯示交易紀錄
@app.route("/")
def index():
    transactions = get_all_transactions()
    total_emission = sum(tx["emission"] for tx in transactions)
    return render_template("index.html", transactions=transactions, total=total_emission)


# ➕ 新增交易
@app.route("/add", methods=["GET", "POST"])
def add_transaction():
    if request.method == "POST":
        date = datetime.now().strftime("%Y-%m-%d")  # 自動記錄日期
        machine = request.form["machine"]
        fertilizer = request.form["fertilizer"]
        amount = float(request.form["amount"])
        emission_factor = MACHINE_EMISSION.get(machine, 1.0)
        emission = amount * emission_factor
        idx = blockchain.new_transaction(date, machine, fertilizer, amount, emission)
        blockchain.new_block(proof=idx)
        return redirect(url_for("index"))

    return render_template("add.html", machines=MACHINE_EMISSION.keys())


if __name__ == "__main__":
    app.run(debug=True)
