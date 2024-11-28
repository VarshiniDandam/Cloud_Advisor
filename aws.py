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
