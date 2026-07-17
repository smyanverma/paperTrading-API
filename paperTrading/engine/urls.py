from django.urls import path
from .views import ProtectedTestView, SignUpView, TransactView, TradeStatusView

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('test-login/', ProtectedTestView.as_view(), name='test_login'),
    path('signup/', SignUpView.as_view(), name='signup'),
    path('login/', TokenObtainPairView.as_view(), name='login'),
    path('login/refresh/', TokenRefreshView.as_view(), name='login_refresh'),
    path('transact/', TransactView.as_view(), name='transact'),
    path('trades/<int:trade_id>/', TradeStatusView.as_view(), name='trade_status'),
]