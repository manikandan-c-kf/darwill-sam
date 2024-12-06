import json
import boto3
import csv
import os
from datetime import datetime

def lambda_handler(event, context):
    try:
        valid_clients = ['apex']
        s3_client = boto3.client('s3')
        sqs_client = client = boto3.client('sqs')
        bucket_name = os.environ['darwill-client-api-app-staging']

        # Validate the client name
        client_name = event['path'].split("/")[2]
        if client_name not in valid_clients:
            raise Exception("Not a valid client.")

        # Check the json payload data
        if not event['body']:
            raise Exception("Not a valid payload. Payload is empty.")

        json_payload = json.loads(event['body'])

        # Check the payload var type
        if type(json_payload) is not dict and type(json_payload) is not list:
            raise Exception ("Not a valid payload. Payload is not supported data type.")

        # Validate the json payload
        validation_status = validate_payload(json_payload, client_name)
        if not validation_status:
            raise Exception("Missing required fields in the payload.")

        # Generate CSV File from Json
        fileName, payload_obj_count =  convert_json_to_csv_file(json_payload, client_name)
        file_path = client_name + "/" + datetime.now().strftime("%Y-%m-%d") + "/" + fileName

        # Upload the payload to S3
        with open('/tmp/' + fileName, "rb") as file_data:
            response = s3_client.put_object(
                Bucket=bucket_name,
                Key=file_path,
                Body=file_data
            )

            if 'ResponseMetadata' in response:
                if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                    sqs_message = json.dumps(
                        {
                            "path": file_path,
                            "count": payload_obj_count,
                            "client_name": client_name
                        }
                    )

                    queue_url = os.environ['LOW_COUNT_QUEUE']
                    if payload_obj_count > 1000:
                        queue_url = os.environ['HIGH_COUNT_QUEUE']

                    sqs_response = sqs_client.send_message(
                        QueueUrl=queue_url,
                        MessageBody=(sqs_message),
                        MessageGroupId=datetime.now().strftime("%Y-%m-%d")
                    )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Successfully processed the payload. Total data processed: " + str(payload_obj_count),
            }),
        }

    except Exception as e:
        print(str(e))
        return {
            "statusCode": 403,
            "body": json.dumps({
                "message": str(e)
            })
        }

# Vaidate the payload
def validate_payload(json_payload, client_name):
    with open('PayloadHeaders.json', 'r') as file:
        check_last_obj = check_first_obj = True
        fields = json.load(file)
        required_fields = fields[client_name + "_customer_fields"]["required"]

        if type(json_payload) is list:
            check_first_obj = check_required_fields_exists(json_payload[0], required_fields)
            if len(json_payload) > 1:
                check_last_obj = check_required_fields_exists(json_payload[-1], required_fields)
        else:
            check_first_obj = check_required_fields_exists(json_payload, required_fields)

        if check_first_obj and check_last_obj:
            return True
        return False

# Check required field exists in the payload
def check_required_fields_exists(json_data, required_fields):
    for field in required_fields:
        if field not in json_data.keys():
            print("Not found field - " + field)
            return False
    return True


# Convert Json to CSV
def convert_json_to_csv_file(json_payload, client_name):
    filename = str(int(datetime.now().timestamp())) + ".csv"

    final_payload = []

    if type(json_payload) is dict:
        final_payload.append(json_payload)
    else:
        final_payload = json_payload

    # Get Header fields
    with open('PayloadHeaders.json', 'r') as file:
        fields = json.load(file)
        header_fields = fields[client_name + "_customer_fields"]["required"] + fields[client_name + "_customer_fields"]["optional"]

    # Create a CSV File
    with open('/tmp/' + filename, mode="w", newline="", encoding="utf-8") as file:
        # Create a CSV writer object
        writer = csv.DictWriter(file, fieldnames=header_fields)

        # Write the header (column names)
        writer.writeheader()

        # Write the data rows
        writer.writerows(final_payload)

    return [filename, len(final_payload)]
