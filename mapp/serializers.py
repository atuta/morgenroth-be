# serializers.py
from rest_framework import serializers
from mapp.models import CustomUser

class UserPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['photo']
