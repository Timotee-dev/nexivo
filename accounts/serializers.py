from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from accounts.models import AuditLog, CustomerProfile, HostProfile, User


class UserPublicSerializer(serializers.ModelSerializer):
    """Minimal, safe-to-expose user representation used inside nested responses."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "avatar", "role"]
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    """Full profile serializer for the authenticated user's own account."""

    class Meta:
        model = User
        fields = [
            "id", "email", "phone_number", "username", "first_name", "last_name",
            "role", "status", "avatar", "bio", "date_of_birth",
            "email_verified", "phone_verified", "created_at",
        ]
        read_only_fields = ["id", "role", "status", "email_verified", "phone_verified", "created_at"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(
        choices=[(User.Role.CUSTOMER, "Customer"), (User.Role.HOST, "Event Host")],
        default=User.Role.CUSTOMER,
    )

    class Meta:
        model = User
        fields = [
            "email", "phone_number", "first_name", "last_name",
            "password", "password_confirm", "role",
        ]

    def validate_phone_number(self, value):
        if value and User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("This phone number is already registered.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        role = validated_data.pop("role", User.Role.CUSTOMER)
        if not validated_data.get("username"):
            base = validated_data["email"].split("@")[0]
            candidate = base
            suffix = 0
            while User.objects.filter(username=candidate).exists():
                suffix += 1
                candidate = f"{base}{suffix}"
            validated_data["username"] = candidate
        user = User(role=role, **validated_data)
        user.set_password(password)
        user.save()

        if role == User.Role.HOST:
            HostProfile.objects.create(user=user)
        else:
            CustomerProfile.objects.create(user=user)

        AuditLog.objects.create(
            actor=user, action=AuditLog.Action.LOGIN, target_model="User",
            target_id=str(user.id), metadata={"event": "registration"},
        )
        return user


class EmailOrPhoneLoginSerializer(serializers.Serializer):
    """
    Accepts either `email` or `phone_number` as the identifier, alongside `password`.
    Custom (non-SimpleJWT-default) serializer because SimpleJWT's TokenObtainPairSerializer
    only supports a single fixed USERNAME_FIELD.
    """

    identifier = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        identifier = attrs["identifier"].strip()
        password = attrs["password"]

        try:
            user_obj = User.objects.get(Q(email__iexact=identifier) | Q(phone_number=identifier))
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid credentials.")

        if user_obj.is_locked:
            raise serializers.ValidationError(
                "Account temporarily locked due to multiple failed login attempts."
            )

        request = self.context.get("request")
        user = authenticate(request=request, username=user_obj.email, password=password)
        if user is None:
            user_obj.failed_login_attempts += 1
            if user_obj.failed_login_attempts >= 5:
                user_obj.lock_account(minutes=15)
            user_obj.save(update_fields=["failed_login_attempts"])
            raise serializers.ValidationError("Invalid credentials.")

        if not user.is_account_active:
            raise serializers.ValidationError(
                f"Account is {user.status}. Contact support for assistance."
            )

        user.failed_login_attempts = 0
        user.save(update_fields=["failed_login_attempts"])
        attrs["user"] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


class HostProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = HostProfile
        fields = [
            "id", "user", "business_name", "business_description", "business_logo",
            "nin_verification_status", "nin_verified", "bank_name", "account_number",
            "account_name", "bank_details_verified", "can_sell_paid_tickets",
            "total_events_created", "total_tickets_sold", "total_revenue",
            "average_rating", "created_at",
        ]
        read_only_fields = [
            "id", "user", "nin_verification_status", "nin_verified",
            "bank_details_verified", "can_sell_paid_tickets",
            "total_events_created", "total_tickets_sold", "total_revenue",
            "average_rating", "created_at",
        ]


class NINSubmissionSerializer(serializers.Serializer):
    nin_number = serializers.CharField(min_length=11, max_length=11)

    def validate_nin_number(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("NIN must be exactly 11 digits.")
        return value


class BankAccountSerializer(serializers.Serializer):
    bank_name = serializers.CharField(max_length=100)
    bank_code = serializers.CharField(max_length=10)
    account_number = serializers.CharField(max_length=20)