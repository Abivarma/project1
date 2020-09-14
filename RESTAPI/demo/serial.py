from rest_framework import serializers
from .models import Book, BookNum, Character


class BookNums(serializers.ModelSerializer):
    class Meta:
        model = BookNum
        fields = ['id', 'isbn_10', 'isbn_13']


class Bookchar(serializers.ModelSerializer):
    class Meta:
        model = Character
        fields = ['id', 'name']

class BookSerial(serializers.ModelSerializer):
    number = BookNums(many=False)
    characters = Bookchar(many=True)

    class Meta:
        model = Book
        fields = ['id', 'title', 'description', 'Price', 'publish_date', 'Covers', 'number', 'characters']
