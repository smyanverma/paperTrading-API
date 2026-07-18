import requests
import time

BASE_URL = "http://localhost:8000/api"

USERNAME = "Mohit"
PASSWORD = "Mohit@123"

def print_step(title, response):
    print(f"\n{'='*50}")
    print(f"{title}  [{response.status_code}]")
    print(f"{'='*50}")
    try:
        print(response.json())
    except Exception:
        print(response.text)


def main():
    # 1. Login
    login_res = requests.post(f"{BASE_URL}/login/", json={
        "username": USERNAME,
        "password": PASSWORD
    })
    print_step("LOGIN", login_res)

    if login_res.status_code != 200:
        print("Login failed, stopping.")
        return

    access_token = login_res.json()["access"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # 2. Check balance
    balance_res = requests.get(f"{BASE_URL}/balance/", headers=headers)
    print_step("CHECK BALANCE", balance_res)

    # 3. Buy NVDA
    buy_res = requests.post(f"{BASE_URL}/transact/", headers=headers, json={
        "ticker": "NVDA",
        "quantity": 1,
        "trade_type": "BUY"
    })
    print_step("BUY NVDA", buy_res)

    if buy_res.status_code != 202:
        print("Buy request failed, stopping.")
        return

    buy_trade_id = buy_res.json()["trade_id"]

    # 4. Poll buy trade until completed
    poll_trade(buy_trade_id, headers, label="BUY")

    # 5. Sell NVDA
    sell_res = requests.post(f"{BASE_URL}/transact/", headers=headers, json={
        "ticker": "NVDA",
        "quantity": 1,
        "trade_type": "SELL"
    })
    print_step("SELL NVDA", sell_res)

    if sell_res.status_code != 202:
        print("Sell request failed, stopping.")
        return

    sell_trade_id = sell_res.json()["trade_id"]

    # 6. Poll sell trade until completed
    poll_trade(sell_trade_id, headers, label="SELL")

    # 7. Check P&L
    pnl_res = requests.get(f"{BASE_URL}/pnl/", headers=headers)
    print_step("PROFIT & LOSS", pnl_res)

    # 8. Check balance again
    balance_res2 = requests.get(f"{BASE_URL}/balance/", headers=headers)
    print_step("CHECK BALANCE (AFTER)", balance_res2)


def poll_trade(trade_id, headers, label="", interval=3, max_attempts=10):
    print(f"\nPolling {label} trade {trade_id}...")
    for attempt in range(max_attempts):
        res = requests.get(f"{BASE_URL}/trades/{trade_id}/", headers=headers)
        data = res.json()
        status = data.get("status")
        print(f"  Attempt {attempt+1}: status = {status}")

        if status in ("COMPLETED", "FAILED"):
            print_step(f"{label} TRADE FINAL STATE", res)
            return

        time.sleep(interval)

    print(f"  Gave up polling after {max_attempts} attempts.")


if __name__ == "__main__":
    main()