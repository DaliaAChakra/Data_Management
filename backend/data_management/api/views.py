from django.shortcuts import get_object_or_404
from django.db import connection
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import TableSchema, FieldSchema
from .serializers import TableSchemaSerializer
from .tasks import import_csv_task
import json
import traceback
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.apps import apps

from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from django.db import models
from django.core.management import call_command

from .services import *
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
import os
class CreateTable(APIView):
    def post(self, request):
        try:
            table_name = request.data.get('name')
            fields = request.data.get('fields')
            message = create_table_service(table_name, fields)
            return Response({'message': message}, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': 'An error occurred while creating the table'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class DeleteTable(APIView):
    def delete(self, request, table_name):
        try:
            print(f"Attempting to delete table: {table_name}")  

            query = f'DROP TABLE IF EXISTS "{table_name}" CASCADE;'
            print(f"Executing query: {query}")

            with connection.cursor() as cursor:
                cursor.execute(query)

            deleted_count, _ = TableSchema.objects.filter(name=table_name).delete()
            if deleted_count == 0:
                print(f"Warning: Table schema '{table_name}' was not found in TableSchema model.")

            return Response({'message': f'Table "{table_name}" deleted successfully'}, status=status.HTTP_200_OK)

        except Exception as e:
            error_message = traceback.format_exc() 
            print(f"Error deleting table: {error_message}") 
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
class TableInfo(APIView):
    def get(self, request, table_name):
        """Retrieve table creation date"""
        try:
            table = get_object_or_404(TableSchema, name=table_name)
            return Response({"created_at": table.created_at}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class CRUDOperations(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication] 
    permission_classes = [IsAuthenticated] 
    
    def get(self, request, table_name):
        """Retrieve all records from a table"""
        query = f'SELECT * FROM "{table_name}"'
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                print(rows)
            return Response(rows, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def post(self, request, table_name):
        """Insert a new record into the table"""
        fields = request.data
        columns = ', '.join(fields.keys())
        values = ', '.join(['%s'] * len(fields))
        
        query = f'INSERT INTO "{table_name}" ({columns}) VALUES ({values})'
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, tuple(fields.values()))
            return Response({'message': 'Record added successfully'}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, table_name):
        """Update an existing record in the table"""
        record_id = request.data.get("id")
        if not record_id:
            return Response({'error': 'ID is required for update'}, status=status.HTTP_400_BAD_REQUEST)
        
        fields = {k: v for k, v in request.data.items() if k != "id"}
        update_query = ", ".join([f'"{key}" = %s' for key in fields.keys()])
        query = f"UPDATE \"{table_name}\" SET {update_query} WHERE id = %s"
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, tuple(fields.values()) + (record_id,))
            return Response({'message': 'Record updated successfully'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, table_name):
        """Delete a record from the table"""
        record_id = request.data.get("id")
        if not record_id:
            return Response({'error': 'ID is required for deletion'}, status=status.HTTP_400_BAD_REQUEST)
        
        query = f"DELETE FROM \"{table_name}\" WHERE id = %s"
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (record_id,))
            return Response({'message': 'Record deleted successfully'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def delete_table(self, request, table_name):
        """Delete an entire table"""
        query = f'DROP TABLE IF EXISTS "{table_name}"'
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
            return Response({'message': f'Table "{table_name}" deleted successfully'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ImportCSV(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication] 
    permission_classes = [IsAuthenticated] 
    """API to import CSV data into a table"""

    def post(self, request, table_name):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'CSV file is required'}, status=status.HTTP_400_BAD_REQUEST)

        file_path = default_storage.save(file.name, ContentFile(file.read()))
        import_csv_task.delay(table_name)

        return Response({"message": "Import started"}, status=status.HTTP_200_OK)
    
class ListTables(APIView):
    def get(self, request):
        if not request.user.is_superuser:
            raise PermissionDenied("You do not have permission to access this resource.")
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
                tables = [row[0] for row in cursor.fetchall()]
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
        
        return JsonResponse({"tables": tables})

    def list_tables(request):
        if not request.user.is_superuser:
            raise PermissionDenied("You do not have permission to access this resource.")
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
                tables = [row[0] for row in cursor.fetchall()]
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
        
        return JsonResponse({"tables": tables})
    


class GetFields(APIView):
    permission_classes = [IsAuthenticated] 

    def get(self, request, table_name):
        if not request.user.is_superuser:
            raise PermissionDenied("You do not have permission to access this resource.")

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
                    [table_name]
                )
                fields = [row[0] for row in cursor.fetchall()]
                print(fields)

            if not fields:
                return JsonResponse({"error": "Table not found"}, status=404)

            return JsonResponse({"fields": fields})
            

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


    def trigger_csv_import(request):

        table_name = request.POST.get("table_name")
        user_email = request.POST.get("email") 

        if not user_email:
            return JsonResponse({"error": "Email is required"}, status=400)

        import_csv_task.delay(file_path, table_name, user_email)
        return JsonResponse({"message": "CSV import task started."})