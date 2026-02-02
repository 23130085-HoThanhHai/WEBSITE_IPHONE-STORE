from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm


class CustomUserCreationForm(UserCreationForm):
    # Thêm các trường mong muốn
    first_name = forms.CharField(
        max_length=30, required=True, help_text='Bắt buộc')
    last_name = forms.CharField(
        max_length=30, required=True, help_text='Bắt buộc')
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        # Các trường hiển thị trong form theo thứ tự
        fields = ("username", "first_name", "last_name", "email")
