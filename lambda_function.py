import json
import boto3
from datetime import datetime, timedelta

ec2 = boto3.client('ec2')
cloudwatch = boto3.client('cloudwatch')

def lambda_handler(event, context):
    method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    path_params = event.get('pathParameters') or {}
    instance_id = path_params.get('id')

    if method == 'POST' and instance_id:
        action = path_params.get('action')
        return handle_action(instance_id, action)
    elif instance_id:
        return get_instance_detail(instance_id)
    else:
        return list_instances()


def handle_action(instance_id, action):
    try:
        if action == 'start':
            ec2.start_instances(InstanceIds=[instance_id])
        elif action == 'stop':
            ec2.stop_instances(InstanceIds=[instance_id])
        elif action == 'reboot':
            ec2.reboot_instances(InstanceIds=[instance_id])
        else:
            return respond({'error': 'Invalid action'}, status=400)

        return respond({'message': f'{action} initiated for {instance_id}'})
    except Exception as e:
        return respond({'error': str(e)}, status=500)
        

def list_instances():
    response = ec2.describe_instances()
    instances = []
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instances.append({
                'instance_id': instance['InstanceId'],
                'state': instance['State']['Name'],
                'instance_type': instance['InstanceType'],
                'public_ip': instance.get('PublicIpAddress', ''),
                'availability_zone': instance['Placement']['AvailabilityZone']
            })
    return respond({'instances': instances})

def get_instance_detail(instance_id):
    response = ec2.describe_instances(InstanceIds=[instance_id])
    reservations = response['Reservations']
    if not reservations:
        return respond({'error': 'Instance not found'}, status=404)

    instance = reservations[0]['Instances'][0]

    tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
    security_groups = [sg['GroupName'] for sg in instance.get('SecurityGroups', [])]
    volumes = [bdm['Ebs']['VolumeId'] for bdm in instance.get('BlockDeviceMappings', []) if 'Ebs' in bdm]

    detail = {
        'instance_id': instance['InstanceId'],
        'state': instance['State']['Name'],
        'instance_type': instance['InstanceType'],
        'public_ip': instance.get('PublicIpAddress', ''),
        'private_ip': instance.get('PrivateIpAddress', ''),
        'availability_zone': instance['Placement']['AvailabilityZone'],
        'vpc_id': instance.get('VpcId', ''),
        'subnet_id': instance.get('SubnetId', ''),
        'launch_time': instance['LaunchTime'].isoformat(),
        'ami_id': instance['ImageId'],
        'key_name': instance.get('KeyName', ''),
        'security_groups': security_groups,
        'volumes': volumes,
        'tags': tags,
        'cpu_metrics': get_metric(instance_id, 'CPUUtilization', 'Average'),
        'network_in_metrics': get_metric(instance_id, 'NetworkIn', 'Sum'),
        'network_out_metrics': get_metric(instance_id, 'NetworkOut', 'Sum')
    }
    return respond({'instance': detail})

def get_metric(instance_id, metric_name, stat):
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=1)

    response = cloudwatch.get_metric_statistics(
        Namespace='AWS/EC2',
        MetricName=metric_name,
        Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
        StartTime=start_time,
        EndTime=end_time,
        Period=300,
        Statistics=[stat]
    )

    datapoints = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
    return [
        {
            'timestamp': dp['Timestamp'].isoformat(),
            'value': round(dp[stat], 2)
        }
        for dp in datapoints
    ]

def respond(body, status=200):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body)
    }