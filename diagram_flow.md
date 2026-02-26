title AWS QR Code Generation Flow
direction right
title AWS QR Code Generation Flow

Clients [icon: users] {
  MTG App [icon: smartphone]
  Cloud Clients App [icon: smartphone, label: "ClientApp"]
}

AWS Cloud Environment [icon: aws-cloud] {
  API Gateway [icon: aws-api-gateway]
  Lambda Function Python Logic [icon: aws-lambda, label: "Lambda Function Generate QRCode"  ]
  DynamoDB Table [icon: aws-dynamodb, label: "DynamoDB Table"]
  S3 Bucket [icon: aws-s3, label: "S3 Bucket"]
}

// Connections
API Gateway > Lambda Function Python Logic: Trigger Event
Lambda Function Python Logic > S3 Bucket: Upload Image
Lambda Function Python Logic > DynamoDB Table: Save Metadata
API Gateway --> Clients: Return QRcode [textSize: medium]
Clients > API Gateway: POST /generate
Clients > AWS Cloud Environment: POST /generate
Lambda Function Python Logic <-- S3 Bucket: Return Image URL
API Gateway <-- Lambda Function Python Logic: Return response
