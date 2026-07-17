from django.shortcuts import render
from django.contrib.auth.models import User
from django.db import transaction  # <-- Added this crucial import!
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, permissions, status
import uuid

from .serializers import SignUpSerializer,TransactSerializer
from .models import UserProfile
from .models import Stock, PortfolioItem, Trade

#celery
from .tasks import execute_trade


class ProtectedTestView(APIView):
    # This line forces the user to provide a valid JWT access token
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "message": f"Hello {request.user.username}, your JWT login is working perfectly!",
            "balance": request.user.profile.balance if hasattr(request.user, 'profile') else "No profile set up yet"
        })


class SignUpView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = SignUpSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Uses the imported database transaction manager to protect data integrity
        with transaction.atomic():
            user = serializer.save()
            UserProfile.objects.create(user=user, balance=100000.00)

        return Response(
            {"message": "Signup successful", "username": user.username},
            status=status.HTTP_201_CREATED
        )


class TransactView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TransactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ticker = serializer.validated_data['ticker']
        quantity = serializer.validated_data['quantity']
        trade_type = serializer.validated_data['trade_type']

        profile = request.user.profile
        stock = Stock.objects.get(ticker=ticker)  # still validated to exist by the serializer

        trade = Trade.objects.create(
            profile=profile,
            stock=stock,
            trade_type=trade_type,
            shares=quantity,
            price_at_execution=None,       # not known yet — filled in once the task actually runs
            status=Trade.Status.PENDING,
            idempotency_key=str(uuid.uuid4()),
        )

        execute_trade.delay(trade.id)

        return Response(
            {
                "message": "Trade request accepted.",
                "trade_id": trade.id,
                "status": trade.status,
            },
            status=status.HTTP_202_ACCEPTED
        )

class CheckBalanceView(APIView):
    # Enforces that the user must provide a valid JWT access token
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # request.user is automatically populated by DRF via the JWT token
            profile = request.user.profile  # Access the related UserProfile
            return Response({
                "username": request.user.username,
                "balance": profile.balance
            }, status=status.HTTP_200_OK)
            
        except UserProfile.DoesNotExist:
            return Response(
                {"error": "Profile not found for this user."}, 
                status=status.HTTP_404_NOT_FOUND
            )


class TradeStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, trade_id):
        try:
            trade = Trade.objects.get(id=trade_id, profile=request.user.profile)
        except Trade.DoesNotExist:
            return Response({"error": "Trade not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "trade_id": trade.id,
            "ticker": trade.stock_id,
            "trade_type": trade.trade_type,
            "shares": trade.shares,
            "status": trade.status,
            "price_at_execution": str(trade.price_at_execution) if trade.price_at_execution else None,
            "failure_reason": trade.failure_reason,
        })