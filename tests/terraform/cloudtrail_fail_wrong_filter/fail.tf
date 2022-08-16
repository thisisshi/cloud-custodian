#fail case: wrong filter

provider "aws" {
  region = "us-east-1"
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "fail-bucket" {
  bucket        = "fail-trail-test-bucket-testing"
  force_destroy = true
      tags = {
    c7n = true
  }
}

resource "aws_s3_bucket_public_access_block" "fail-bucket-block" {
  bucket = aws_s3_bucket.fail-bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "fail-policy" {
  bucket = aws_s3_bucket.fail-bucket.id

     policy = <<POLICY
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AWSCloudTrailAclCheck20150319",
            "Effect": "Allow",
            "Principal": {
                "Service": "cloudtrail.amazonaws.com"
            },
            "Action": "s3:GetBucketAcl",
            "Resource": "arn:aws:s3:::${aws_s3_bucket.fail-bucket.bucket}",
            "Condition": {
                "StringEquals": {
                    "AWS:SourceArn": "arn:aws:cloudtrail:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:trail/fail-tf-trail-3bf19dec-127e-11ed-861d-0242ac12000"
                }
            }
        },
        {
            "Sid": "AWSCloudTrailWrite20150319",
            "Effect": "Allow",
            "Principal": {
                "Service": "cloudtrail.amazonaws.com"
            },
            "Action": "s3:PutObject",
            "Resource": "arn:aws:s3:::${aws_s3_bucket.fail-bucket.bucket}/*",
            "Condition": {
                "StringEquals": {
                    "AWS:SourceArn": "arn:aws:cloudtrail:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:trail/fail-tf-trail-3bf19dec-127e-11ed-861d-0242ac12000",
                    "s3:x-amz-acl": "bucket-owner-full-control"
                }
            }
        }
    ]
}
POLICY
}

resource "aws_cloudtrail" "fail-cloudtrail" {
  name                          = "fail-tf-trail-3bf19dec-127e-11ed-861d-0242ac12000"
  s3_bucket_name                = aws_s3_bucket.fail-bucket.bucket
  s3_key_prefix                 = ""
  include_global_service_events = true
  is_multi_region_trail = true

  event_selector {
    read_write_type           = "All"
    include_management_events = true

    data_resource {
      type = "AWS::S3::Object"

      # Make sure to append a trailing '/' to your ARN if you want
      # to monitor all objects in a bucket.
      values = ["${aws_s3_bucket.fail-bucket.arn}/"]
    }
  }
  tags = {
    c7n = true
  }
  depends_on = [
    aws_s3_bucket_policy.fail-policy
  ]
}




