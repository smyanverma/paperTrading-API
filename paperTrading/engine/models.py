from django.db import models
from django.contrib.auth.models import User


# 1. Available Stocks
class Stock(models.Model):
    ticker = models.CharField(max_length=10, unique=True, primary_key=True)
    company_name = models.CharField(max_length=255)
    current_price = models.DecimalField(max_digits=10, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.ticker


# 2. User Profile & Cash Balance
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=100000.00)  # Starts with $100k

    def __str__(self):
        return f"{self.user.username}'s Profile"


# 3. Tickers Owned (The Portfolio)
class PortfolioItem(models.Model):
    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='portfolio_items')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    shares = models.IntegerField(default=0)
    # Nullable: a position with 0 shares (not yet bought, or fully sold) has no meaningful avg price
    average_buy_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['profile', 'stock'], name='unique_profile_stock')
        ]

    def __str__(self):
        return f"{self.profile.user.username} owns {self.shares} of {self.stock.ticker}"


# 4. Trade requests — the async execution record + idempotency + history
class Trade(models.Model):
    class TradeType(models.TextChoices):
        BUY = 'BUY', 'Buy'
        SELL = 'SELL', 'Sell'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='trades')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    trade_type = models.CharField(max_length=4, choices=TradeType.choices)

    # What the user asked for (e.g. "$1000 of NVDA") — useful to keep the original intent around
    amount_usd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    shares = models.IntegerField(null=True, blank=True)  # resolved once price is known (whole shares only)

    price_at_execution = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    # Client-supplied or server-generated key to dedupe retried requests
    idempotency_key = models.CharField(max_length=64, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.trade_type} {self.stock_id} for {self.profile.user.username} [{self.status}]"