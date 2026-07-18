import uuid
from decimal import Decimal
from celery import shared_task
from django.db import transaction

from .models import Stock, PortfolioItem, Trade, UserProfile

#celery beat
import os
import requests
FINNHUB_API_KEY = os.environ.get('FINNHUB_API_KEY')
#redis cache
from django.core.cache import cache


@shared_task
def execute_trade(trade_id):
    try:
        trade = Trade.objects.get(id=trade_id)
    except Trade.DoesNotExist:
        return {"error": f"Trade {trade_id} not found."}

    ticker = trade.stock_id
    quantity = trade.shares
    trade_type = trade.trade_type

    try:
        with transaction.atomic():
            # Re-fetch and lock fresh from DB — never trust in-memory state passed across processes
            profile = UserProfile.objects.select_for_update().get(pk=trade.profile_id)
            stock = Stock.objects.get(ticker=ticker)
            cost = stock.current_price * quantity

            portfolio_item, _ = PortfolioItem.objects.select_for_update().get_or_create(
                profile=profile, stock=stock,
                defaults={'shares': 0, 'average_buy_price': None}
            )

            if trade_type == 'BUY':
                if profile.balance < cost:
                    trade.status = Trade.Status.FAILED
                    trade.failure_reason = "Insufficient balance."
                    trade.save()
                    return {"status": "FAILED", "reason": "Insufficient balance."}

                existing_value = (portfolio_item.average_buy_price or Decimal('0')) * portfolio_item.shares
                new_total_shares = portfolio_item.shares + quantity
                portfolio_item.average_buy_price = (existing_value + cost) / new_total_shares
                portfolio_item.shares = new_total_shares
                portfolio_item.save()

                profile.balance -= cost
                profile.save()

            else:  # SELL
                if portfolio_item.shares < quantity:
                    trade.status = Trade.Status.FAILED
                    trade.failure_reason = "Not enough shares to sell."
                    trade.save()
                    return {"status": "FAILED", "reason": "Not enough shares to sell."}

                portfolio_item.shares -= quantity
                if portfolio_item.shares == 0:
                    portfolio_item.average_buy_price = None
                portfolio_item.save()

                profile.balance += cost
                profile.save()
            

            trade.price_at_execution = stock.current_price
            trade.status = Trade.Status.COMPLETED
            trade.save()
        
        #invalidate the cached p&l 
        cache.delete(f"pnl:user_{profile.user_id}")

        return {"status": "COMPLETED", "trade_id": trade.id}

    except Exception as e:
        trade.status = Trade.Status.FAILED
        trade.failure_reason = str(e)
        trade.save()
        return {"status": "FAILED", "reason": str(e)}



@shared_task
def refresh_stock_prices():
    tickers = list(Stock.objects.values_list('ticker', flat=True))
    if not tickers:
        return {"updated": 0}

    updated = 0
    for ticker in tickers:
        try:
            response = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": ticker, "token": FINNHUB_API_KEY},
                timeout=5
            )
            response.raise_for_status()
            data = response.json()
            price = data.get('c')  # 'c' = current price in Finnhub's response

            if not price or price == 0:
                print(f"No valid price for {ticker}, skipping.")
                continue

            Stock.objects.filter(ticker=ticker).update(current_price=price)
            updated += 1
        except Exception as e:
            print(f"Failed to update {ticker}: {e}")

    return {"updated": updated}