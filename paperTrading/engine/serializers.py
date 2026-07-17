from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from .models import Stock

class SignUpSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def create(self, validated_data):
        # create_user hashes the password properly — never use User.objects.create() directly
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password']
        )
        return user

class TransactSerializer(serializers.Serializer):
    ticker = serializers.CharField(max_length=10)
    quantity = serializers.IntegerField(min_value=1)
    trade_type = serializers.ChoiceField(choices=['BUY', 'SELL'])

    def validate_ticker(self, value):
        value = value.upper()
        if not Stock.objects.filter(ticker=value).exists():
            raise serializers.ValidationError(f"Stock '{value}' does not exist.")
        return value