from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('engine.urls')), # Points to your engine app routes
    
    # --- THIS IS YOUR LOGIN SYSTEM ---
    # Sending a username/password here acts as your "Login" and gives you tokens
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    
    # Sending an expired token here refreshes your login session
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]