from flask import Flask, jsonify
import boto3
import pymysql
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

app = Flask(__name__)

# Accessing environment variables
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION')

# AWS Cost Explorer Client
client = boto3.client('ce', region_name='us-east-1')

# AWS EC2 Client (Ensure it's defined at the beginning)
ec2_client = boto3.client('ec2', region_name='us-east-1')  # AWS EC2 client for describing instances

# AWS S3 Client
s3_client = boto3.client('s3', region_name='us-east-1')  # AWS S3 client for listing buckets

rds_client = boto3.client('rds', region_name='us-east-1')

# Configure the MySQL database URI to connect to your RDS instance
# app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://admin:Varshini7378@database-1.cfa6aie0ilu9.us-east-1.rds.amazonaws.com:3306/cost_usage_db'
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# db = SQLAlchemy(app)

# MySQL Database Connection
def get_db_connection():
    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME')
    )


def fetch_cost_data():
    try:
        today = datetime.today()
        start_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')  # Last 30 days
        end_date = today.strftime('%Y-%m-%d')

        response = client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='DAILY',
            Metrics=['UnblendedCost', 'UsageQuantity'],
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                {'Type': 'DIMENSION', 'Key': 'REGION'}
            ]
        )
        
        print("AWS Response:", response)  # Add this line to print the response
        return response.get('ResultsByTime', [])
    except Exception as e:
        print(f"Error fetching data from AWS: {e}")
        raise


# Function to insert cost data into MySQL
def insert_cost_data(cost_data):
    db = get_db_connection()
    try:
        cursor = db.cursor()

        for day_data in cost_data:
            cost_date = day_data['TimePeriod']['Start']
            for group in day_data['Groups']:
                service_type = group['Keys'][0]
                region = group['Keys'][1]
                cost_amount = float(group['Metrics']['UnblendedCost']['Amount'])
                usage_type = group['Keys'][1]  # Add appropriate usage type if available
                total_cost = cost_amount

                # SQL Insert Command
                sql = """
                    INSERT INTO cost (
                        cost_date, service_type, region, cost_amount, usage_type, total_cost
                    ) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                """

                # Execute SQL Command
                cursor.execute(sql, (cost_date, service_type, region, cost_amount, usage_type, total_cost))

        # Commit changes to the database
        db.commit()
        print("Data committed to the database.")
    except Exception as e:
        print(f"Error inserting data into the database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


@app.route('/fetch-and-insert-cost-data', methods=['GET'])
def fetch_and_insert_cost_data():
    try:
        print("Fetching AWS cost data...")
        cost_data = fetch_cost_data()
        if not cost_data:
            return jsonify({"message": "No cost data available for the given period."}), 200
        else:
            print("Inserting data into MySQL...")
            insert_cost_data(cost_data)
            return jsonify({"message": "Cost data successfully inserted into the database."}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


# Flask route to check server status
@app.route('/status', methods=['GET'])
def status():
    return jsonify({"message": "Server is running."}), 200

def fetch_ec2_data():
    try:
        # Describe EC2 instances
        instances = ec2_client.describe_instances()
        
        # Print the raw response to check if EC2 instances are returned
        print(instances)  # Add this line to print the response
        
        ec2_data = []  # List to store EC2 instance data
        
        # Loop through the instances and extract relevant details
        for reservation in instances['Reservations']:
            for instance in reservation['Instances']:
                ec2_data.append({
                    'instance_id': instance['InstanceId'],
                    'instance_type': instance['InstanceType'],
                    'state': instance['State']['Name'],
                    'private_ip': instance.get('PrivateIpAddress'),
                    'public_ip': instance.get('PublicIpAddress'),
                    'launch_time': instance['LaunchTime'],
                    'total_cost': 0.00,  # Placeholder for cost data
                    'start_date': datetime.today().strftime('%Y-%m-%d'),
                    'end_date': datetime.today().strftime('%Y-%m-%d'),
                    'hours_used': 0.0,  # Placeholder for usage data
                    'per_unit_cost_usd': 0.0,  # Placeholder for cost per unit
                    'cpu_utilization': 0.0,  # Placeholder for CPU utilization
                    'memory_utilization_mb': 0.0,  # Placeholder for memory utilization
                    'cpu_max': 0.0,  # Placeholder for max CPU usage
                    'max_memory_util': 0.0  # Placeholder for max memory usage
                })

        return ec2_data  # Return the extracted EC2 data

    except Exception as e:
        print(f"Error fetching EC2 data from AWS: {e}")
        raise


# Function to insert EC2 instance data into MySQL
def insert_ec2_data(ec2_data):
    cursor = db.cursor()
    try:
        for data in ec2_data:
            # SQL Insert Command
            sql = """
                INSERT INTO ec2_instances 
                (instance_id, instance_type, launch_time, state, private_ip, public_ip, 
                total_cost, Start_Date, End_Date, Hours_Used, Per_Unit_Cost_USD, 
                CPU_Utilization, Memory_Utilization_MB, cpu_max, MAX_MEMORY_UTIL)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            # Execute SQL Command
            cursor.execute(sql, (
                data['instance_id'], data['instance_type'], data['launch_time'], data['state'], 
                data['private_ip'], data['public_ip'], data['total_cost'], data['start_date'], 
                data['end_date'], data['hours_used'], data['per_unit_cost_usd'], 
                data['cpu_utilization'], data['memory_utilization_mb'], data['cpu_max'], data['max_memory_util']
            ))

        # Commit changes to the database
        db.commit()
        print("EC2 data committed to the database.")
    except Exception as e:
        print(f"Error inserting EC2 data into the database: {e}")
        db.rollback()
        raise
    finally:
        cursor.close()

# Flask route to fetch and insert EC2 data
@app.route('/fetch-and-insert-ec2-data', methods=['GET'])
def fetch_and_insert_ec2_data():
    try:
        ec2_data = fetch_ec2_data()
        if not ec2_data:
            return jsonify({"message": "No EC2 data available."}), 200
        else:
            insert_ec2_data(ec2_data)
            return jsonify({"message": "EC2 data successfully inserted into the database."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
def fetch_s3_data():
    try:
        # List all S3 buckets
        response = s3_client.list_buckets()
        
        s3_data = []
        
        # Extract relevant S3 bucket data
        for bucket in response['Buckets']:
            s3_data.append({
                'bucket_name': bucket['Name'],
                'creation_date': bucket['CreationDate'],
                'region': 'us-east-1',  # Assuming all buckets are in 'us-east-1', you can fetch it dynamically if needed
                'total_usage': 0.0,  # Placeholder for total usage
                'total_cost': 0.0,  # Placeholder for cost data
                'instance_type': 'N/A',  # Placeholder for instance type
                'start_date': datetime.today().strftime('%Y-%m-%d'),
                'end_date': datetime.today().strftime('%Y-%m-%d'),
                'hours_used': 0.0,  # Placeholder for hours used
                'per_unit_cost_usd': 0.0,  # Placeholder for cost per unit
                'cpu_utilization': 0.0,  # Placeholder for CPU utilization
                'memory_utilization_mb': 0.0,  # Placeholder for memory utilization
                'cpu_max': 0.0,  # Placeholder for max CPU usage
                'max_memory_util': 0.0  # Placeholder for max memory usage
            })

        return s3_data
    except Exception as e:
        print(f"Error fetching S3 data from AWS: {e}")
        raise


# Function to insert S3 bucket data into MySQL
def insert_s3_data(s3_data):
    db = get_db_connection()
    try:
        cursor = db.cursor()
        
        for data in s3_data:
            # SQL Insert Command
            sql = """
                INSERT INTO s3_buckets 
                (bucket_name, creation_date, region, total_usage, total_cost, instance_type, 
                start_date, end_date, hours_used, per_unit_cost_usd, cpu_utilization, 
                memory_utilization_mb, cpu_max, max_memory_util)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            # Execute SQL Command
            cursor.execute(sql, (
                data['bucket_name'], data['creation_date'], data['region'], data['total_usage'], 
                data['total_cost'], data['instance_type'], data['start_date'], data['end_date'], 
                data['hours_used'], data['per_unit_cost_usd'], data['cpu_utilization'], 
                data['memory_utilization_mb'], data['cpu_max'], data['max_memory_util']
            ))

        # Commit changes to the database
        db.commit()
        print("S3 bucket data committed to the database.")
    except Exception as e:
        print(f"Error inserting S3 data into the database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


@app.route('/fetch-and-insert-s3-data', methods=['GET'])
def fetch_and_insert_s3_data():
    try:
        s3_data = fetch_s3_data()
        if not s3_data:
            return jsonify({"message": "No S3 bucket data available."}), 200
        else:
            insert_s3_data(s3_data)
            return jsonify({"message": "S3 bucket data successfully inserted into the database."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
def fetch_rds_data():
    try:
        response = rds_client.describe_db_instances()
        rds_data = []

        for db_instance in response['DBInstances']:
            rds_data.append({
                'db_instance_id': db_instance.get('DBInstanceIdentifier'),
                'db_instance_class': db_instance.get('DBInstanceClass'),
                'db_engine': db_instance.get('Engine'),
                'db_status': db_instance.get('DBInstanceStatus'),
                'master_username': db_instance.get('MasterUsername'),
                'endpoint_address': db_instance['Endpoint'].get('Address') if 'Endpoint' in db_instance else None,
                'endpoint_port': db_instance['Endpoint'].get('Port') if 'Endpoint' in db_instance else None,
                'vpc_id': db_instance.get('DBSubnetGroup', {}).get('VpcId'),
                'availability_zone': db_instance.get('AvailabilityZone'),
                'multi_az': db_instance.get('MultiAZ'),
                'backup_retention_period': db_instance.get('BackupRetentionPeriod'),
                'tags': str(rds_client.list_tags_for_resource(
                    ResourceName=db_instance.get('DBInstanceArn')
                ).get('TagList', [])),
                'storage_encrypted': db_instance.get('StorageEncrypted'),
                'instance_create_time': db_instance.get('InstanceCreateTime'),
                'license_model': db_instance.get('LicenseModel'),
                'cost': 0.0,  # Placeholder for cost data
                'usage_quantity': 0.0,  # Placeholder for usage data
                'total_cost': 0.0,  # Placeholder for total cost
                'instance_type': db_instance.get('DBInstanceClass'),
                'start_date': datetime.today().strftime('%Y-%m-%d'),
                'end_date': datetime.today().strftime('%Y-%m-%d'),
                'hours_used': 0.0,  # Placeholder for hours used
                'per_unit_cost_usd': 0.0,  # Placeholder for cost per unit
                'cpu_utilization': 0.0,  # Placeholder for CPU utilization
                'memory_utilization_mb': 0.0,  # Placeholder for memory utilization
                'cpu_max': 0.0,  # Placeholder for max CPU usage
                'max_memory_util': 0.0  # Placeholder for max memory usage
            })

        return rds_data
    except Exception as e:
        print(f"Error fetching RDS data from AWS: {e}")
        raise
    
def insert_rds_data(rds_data):
    db = get_db_connection()
    try:
        cursor = db.cursor()

        for data in rds_data:
            sql = """
                INSERT INTO rds_instances
                (db_instance_id, db_instance_class, db_engine, db_status, master_username, 
                endpoint_address, endpoint_port, vpc_id, availability_zone, multi_az, 
                backup_retention_period, tags, storage_encrypted, instance_create_time, 
                license_model, cost, usage_quantity, total_cost, Instance_Type, Start_Date, 
                End_Date, Hours_Used, Per_Unit_Cost_USD, CPU_Utilization, 
                Memory_Utilization_MB, cpu_max, MAX_MEMORY_UTIL)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                data['db_instance_id'], data['db_instance_class'], data['db_engine'], 
                data['db_status'], data['master_username'], data['endpoint_address'], 
                data['endpoint_port'], data['vpc_id'], data['availability_zone'], 
                data['multi_az'], data['backup_retention_period'], data['tags'], 
                data['storage_encrypted'], data['instance_create_time'], 
                data['license_model'], data['cost'], data['usage_quantity'], 
                data['total_cost'], data['instance_type'], data['start_date'], 
                data['end_date'], data['hours_used'], data['per_unit_cost_usd'], 
                data['cpu_utilization'], data['memory_utilization_mb'], 
                data['cpu_max'], data['max_memory_util']
            ))

        db.commit()
        print("RDS data committed to the database.")
    except Exception as e:
        print(f"Error inserting RDS data into the database: {e}")
        db.rollback()
        raise
    finally:
        db.close()
        
@app.route('/fetch-and-insert-rds-data', methods=['GET'])
def fetch_and_insert_rds_data():
    try:
        rds_data = fetch_rds_data()
        if not rds_data:
            return jsonify({"message": "No RDS instance data available."}), 200
        else:
            insert_rds_data(rds_data)
            return jsonify({"message": "RDS instance data successfully inserted into the database."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
def fetch_rds_data():
    try:
        response = rds_client.describe_db_instances()
        rds_data = []

        for db_instance in response['DBInstances']:
            rds_data.append({
                'instance_type': db_instance.get('DBInstanceClass'),
                'start_date': datetime.today().strftime('%Y-%m-%d'),
                'end_date': datetime.today().strftime('%Y-%m-%d'),
                'region': db_instance.get('AvailabilityZone', 'unknown-region'),
                'hours_used': 0.0,  # Placeholder for hours used
                'per_unit_cost_usd': 0.0,  # Placeholder for cost per unit
                'total_cost_usd': 0.0,  # Placeholder for total cost
                'cpu_utilization_percent': 0.0,  # Placeholder for CPU utilization
                'memory_utilization_mb': 0.0,  # Placeholder for memory utilization
                'cpu_max': 0.0,  # Placeholder for max CPU usage
                'max_memory_util': 0.0  # Placeholder for max memory usage
            })

        return rds_data
    except Exception as e:
        print(f"Error fetching RDS data from AWS: {e}")
        raise
    
def insert_rds_data(rds_data):
    db = get_db_connection()
    try:
        cursor = db.cursor()

        for data in rds_data:
            sql = """
                INSERT INTO instance_usage 
                (instance_type, start_date, end_date, region, hours_used, 
                per_unit_cost_usd, total_cost_usd, cpu_utilization_percent, 
                memory_utilization_mb, cpu_max, max_memory_util)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                data['instance_type'], data['start_date'], data['end_date'], 
                data['region'], data['hours_used'], data['per_unit_cost_usd'], 
                data['total_cost_usd'], data['cpu_utilization_percent'], 
                data['memory_utilization_mb'], data['cpu_max'], data['max_memory_util']
            ))

        db.commit()
        print("Instance usage data committed to the database.")
    except Exception as e:
        print(f"Error inserting instance usage data into the database: {e}")
        db.rollback()
        raise
    finally:
        db.close()
        
@app.route('/fetch-and-insert-instance-usage', methods=['GET'])
def fetch_and_insert_instance_usage():
    try:
        rds_data = fetch_rds_data()
        if not rds_data:
            return jsonify({"message": "No instance usage data available."}), 200
        else:
            insert_rds_data(rds_data)
            return jsonify({"message": "Instance usage data successfully inserted into the database."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'], endpoint='health_check')
def status():
    return jsonify({"message": "Health check is OK."}), 200

# Test endpoint to check database connection
@app.route('/test', methods=['GET'])
def test_api():
    try:
        # Execute raw SQL query using db.session.execute() with text()
        result = db.cursor().execute('SELECT 1')
        # Fetch the result and return it in the response
        return jsonify({"status": "success", "message": "Database connected!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)

# Import necessary libraries at the top
import boto3
from botocore.exceptions import ClientError
from flask import Flask, jsonify
import mysql.connector
import json

# Initialize Flask app
app = Flask(__name__)

# MySQL Connection configuration
db_config = {
    'host': 'localhost',
    'user': 'flask_app_user',
    'password': 'securepassword123',
    'database': 'cost_usage_db'
}

# AWS Client creation function
def create_aws_clients():
    ec2_client = boto3.client('ec2', region_name='us-east-1')
    rds_client = boto3.client('rds', region_name='us-east-1')
    s3_client = boto3.client('s3')
    ce_client = boto3.client('ce', region_name='us-east-1')
    return ec2_client, rds_client, s3_client, ce_client

# Get EC2, RDS, and S3 resources
@app.route('/get-resources', methods=['GET'])
def get_resources():
    try:
        ec2_client, rds_client, s3_client, ce_client = create_aws_clients()

        # EC2 instances
        ec2_response = ec2_client.describe_instances()
        ec2_instances = [
            {
                'InstanceId': instance['InstanceId'],
                'InstanceType': instance['InstanceType'],
                'State': instance['State']['Name'],
                'LaunchTime': str(instance['LaunchTime'])
            }
            for reservation in ec2_response['Reservations']
            for instance in reservation['Instances']
        ]

        # RDS instances
        rds_response = rds_client.describe_db_instances()
        rds_instances = [
            {
                'DBInstanceIdentifier': db_instance['DBInstanceIdentifier'],
                'DBInstanceClass': db_instance['DBInstanceClass'],
                'Engine': db_instance['Engine'],
                'StorageType': db_instance['StorageType'],
                'AllocatedStorage': db_instance['AllocatedStorage']
            }
            for db_instance in rds_response['DBInstances']
        ]

        # S3 buckets
        s3_response = s3_client.list_buckets()
        s3_buckets = [
            {
                'BucketName': bucket['Name'],
                'CreationDate': str(bucket['CreationDate'])
            }
            for bucket in s3_response['Buckets']
        ]

        return jsonify({
            'EC2 Instances': ec2_instances,
            'RDS Instances': rds_instances,
            'S3 Buckets': s3_buckets
        })

    except ClientError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/get-cost-usage', methods=['GET'])
def get_cost_usage():
    try:
        _, _, _, ce_client = create_aws_clients()

        response = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': '2024-10-01',
                'End': '2024-10-21'
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost', 'UsageQuantity'],
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                {'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'},
            ]
        )

        cost_usage_data = response['ResultsByTime']

        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        for period in cost_usage_data:
            for group in period['Groups']:
                resource_id = group['Keys'][0]
                usage_type = group['Keys'][1]
                unblended_cost = float(group['Metrics']['UnblendedCost']['Amount'])
                usage_amount = float(group['Metrics']['UsageQuantity']['Amount'])

                # Assuming `region` is optional; default to None if undefined
                region = group.get('Region', None)  

                try:
                    cursor.execute('''
                    INSERT INTO cost 
                    (cost_amount, currency, billing_period, service_type, resource_id, cost_date, usage_type, region, total_cost)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (unblended_cost, 'USD', period['TimePeriod']['Start'], usage_type, resource_id, period['TimePeriod']['Start'], usage_type, region, unblended_cost))
                    conn.commit()
                except Exception as e:
                    print("Error inserting data:", e)

        cursor.close()
        conn.close()

        return jsonify(cost_usage_data)

    except ClientError as e:
        return jsonify({'error': str(e)}), 400
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500

# Get S3 resource details
@app.route('/get-s3-resources', methods=['GET'])
def get_s3_resources():
    try:
        _, _, s3_client, ce_client = create_aws_clients()

        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        s3_response = s3_client.list_buckets()
        s3_buckets = []

        for bucket in s3_response['Buckets']:
            bucket_name = bucket['Name']
            creation_date = bucket['CreationDate'].strftime('%Y-%m-%d %H:%M:%S')

            region = s3_client.get_bucket_location(Bucket=bucket_name)['LocationConstraint']

            usage_response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': '2024-10-01', 'End': '2024-10-21'},
                Granularity='DAILY',
                Metrics=['UsageQuantity', 'UnblendedCost'],
                Filter={'Dimensions': {'Key': 'SERVICE', 'Values': ['Amazon Simple Storage Service']}}
            )

            total_usage, total_cost = 0, 0.0
            for period in usage_response['ResultsByTime']:
                for group in period['Groups']:
                    total_usage += float(group['Metrics']['UsageQuantity']['Amount'])
                    total_cost += float(group['Metrics']['UnblendedCost']['Amount'])

            s3_buckets.append({
                'bucket_name': bucket_name,
                'creation_date': creation_date,
                'region': region,
                'total_usage': total_usage,
                'total_cost': total_cost
            })

            cursor.execute('''INSERT INTO s3_buckets (bucket_name, creation_date, region, total_usage, total_cost)
                            VALUES (%s, %s, %s, %s, %s)''',
                        (bucket_name, creation_date, region, total_usage, total_cost))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(s3_buckets)

    except ClientError as e:
        return jsonify({'error': str(e)}), 400
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500


# Fetch EC2 data and insert into MySQL
@app.route('/fetch-ec2-data', methods=['GET'])
def fetch_ec2_data():
    ec2_client, _, _, _ = create_aws_clients()
    connection = None
    cursor = None

    try:
        response = ec2_client.describe_instances()
        instances = response['Reservations']

        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        for reservation in instances:
            for instance in reservation['Instances']:
                instance_info = {
                    'instance_id': instance['InstanceId'],
                    'instance_type': instance['InstanceType'],
                    'launch_time': instance['LaunchTime'].strftime('%Y-%m-%d %H:%M:%S'),
                    'state': instance['State']['Name'],
                    'private_ip': instance.get('PrivateIpAddress', 'N/A'),
                    'public_ip': instance.get('PublicIpAddress', 'N/A'),
                }

                cursor.execute('''INSERT INTO ec2_instances (instance_id, instance_type, launch_time, state, private_ip, public_ip)
                                VALUES (%s, %s, %s, %s, %s, %s)''',
                                (instance_info['instance_id'], instance_info['instance_type'], instance_info['launch_time'],
                                instance_info['state'], instance_info['private_ip'], instance_info['public_ip']))

        connection.commit()
        return jsonify({'message': 'EC2 data fetched and stored successfully.'})

    except ClientError as e:
        return jsonify({'error': str(e)}), 400
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def get_rds_cost(instance_id, start_date, end_date):
    ce_client = boto3.client('ce', region_name='us-east-1')

    # Retrieve cost data for the specific RDS instance
    response = ce_client.get_cost_and_usage(
        TimePeriod={
            'Start': start_date,
            'End': end_date
        },
        Granularity='DAILY',
        Metrics=['BlendedCost'],
        Filter={
            'Dimensions': {
                'Key': 'RESOURCE_ID',
                'Values': [instance_id]
            }
        }
    )

    total_cost = 0.0
    if 'ResultsByTime' in response:
        for result in response['ResultsByTime']:
            for group in result.get('Groups', []):
                total_cost += float(group['Metrics']['BlendedCost']['Amount'])

    return total_cost

# API to get RDS instance data
@app.route('/get-rds-data', methods=['GET'])
def get_rds_data():
    rds_client = None
    connection = None
    cursor = None

    try:
        _, rds_client, _, _ = create_aws_clients()

        # Fetch RDS instances
        response = rds_client.describe_db_instances()
        rds_instances = response['DBInstances']

        # Connect to MySQL
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        # Prepare list to store RDS data
        rds_data_to_insert = []

        for instance in rds_instances:
            rds_data = {
                'db_instance_id': instance['DBInstanceIdentifier'],
                'db_instance_class': instance.get('DBInstanceClass'),
                'db_engine': instance.get('Engine'),
                'db_status': instance.get('DBInstanceStatus'),
                'db_instance_status': instance.get('DBInstanceStatus'),
                'master_username': instance.get('MasterUsername'),
                'endpoint_address': instance['Endpoint']['Address'] if 'Endpoint' in instance else None,
                'endpoint_port': instance['Endpoint']['Port'] if 'Endpoint' in instance else None,
                'vpc_id': instance.get('DBSubnetGroup', {}).get('VpcId'),
                'availability_zone': instance.get('AvailabilityZone'),
                'multi_az': instance.get('MultiAZ'),
                'backup_retention_period': instance.get('BackupRetentionPeriod'),
                'tags': json.dumps(instance.get('TagList', [])),  # Convert tags to JSON string
                'storage_encrypted': instance.get('StorageEncrypted'),
                'instance_create_time': instance.get('InstanceCreateTime'),
                'license_model': instance.get('LicenseModel'),
                'cost': None,  # To be populated if needed
                'usage_quantity': None  # To be populated if needed
            }

            rds_data_to_insert.append(rds_data)

            # Insert into MySQL
            cursor.execute('''
            INSERT INTO rds_instances (
                db_instance_id, db_instance_class, db_engine, 
                db_status, db_instance_status, master_username, 
                endpoint_address, endpoint_port, vpc_id, 
                availability_zone, multi_az, backup_retention_period, 
                tags, storage_encrypted, instance_create_time, 
                license_model, cost, usage_quantity
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            rds_data['db_instance_id'], rds_data['db_instance_class'], 
            rds_data['db_engine'], rds_data['db_status'], 
            rds_data['db_instance_status'], rds_data['master_username'], 
            rds_data['endpoint_address'], rds_data['endpoint_port'], 
            rds_data['vpc_id'], rds_data['availability_zone'], 
            rds_data['multi_az'], rds_data['backup_retention_period'], 
            rds_data['tags'], rds_data['storage_encrypted'], 
            rds_data['instance_create_time'], rds_data['license_model'], 
            rds_data['cost'], rds_data['usage_quantity']
        ))

        connection.commit()
        return jsonify({'message': 'RDS data fetched and stored successfully.', 'data': rds_data_to_insert})

    except ClientError as e:
        return jsonify({'error': str(e)}), 400
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

if __name__ == '__main__':
    app.run(debug=True)
