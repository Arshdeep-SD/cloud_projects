# q2/query_papers.py
import argparse
import json
import time
import boto3
from boto3.dynamodb.conditions import Key

def table_resource(region, table):
    dynamo = boto3.resource('dynamodb', region_name=region)
    return dynamo.Table(table)

def recent(table, category, limit=20):
    pk = f"CATEGORY#{category}"
    start = time.time()
    resp = table.query(KeyConditionExpression=Key('PK').eq(pk), ScanIndexForward=False, Limit=limit)
    elapsed = (time.time() - start) * 1000.0
    items = resp.get('Items', [])
    return {"query_type":"recent_in_category","parameters":{"category":category,"limit":limit},"results":items,"count":len(items),"execution_time_ms":int(elapsed)}

def author(table, author_name):
    # Query the AuthorIndex
    gpk = f"AUTHOR#{author_name}"
    start = time.time()
    resp = table.query(IndexName='AuthorIndex', KeyConditionExpression=Key('GSI1PK').eq(gpk))
    elapsed = (time.time() - start) * 1000.0
    items = resp.get('Items', [])
    return {"query_type":"papers_by_author","parameters":{"author":author_name},"results":items,"count":len(items),"execution_time_ms":int(elapsed)}

def get_paper(table, arxiv_id):
    gpk = f"ARXIV#{arxiv_id}"
    gsk = f"META#{arxiv_id}"
    start = time.time()
    resp = table.query(IndexName='PaperIdIndex', KeyConditionExpression=Key('GSI2PK').eq(gpk) & Key('GSI2SK').eq(gsk))
    elapsed = (time.time() - start) * 1000.0
    items = resp.get('Items', [])
    return {"query_type":"get_by_id","parameters":{"arxiv_id":arxiv_id},"results":items,"count":len(items),"execution_time_ms":int(elapsed)}

def daterange(table, category, start_date, end_date):
    pk = f"CATEGORY#{category}"
    # SK format is YYYY-MM-DD#arxiv_id, so simple lexicographic between works
    start_key = f"{start_date}#"
    end_key = f"{end_date}#~"
    start = time.time()
    resp = table.query(KeyConditionExpression=Key('PK').eq(pk) & Key('SK').between(start_key, end_key), ScanIndexForward=True)
    elapsed = (time.time() - start) * 1000.0
    items = resp.get('Items', [])
    return {"query_type":"daterange_category","parameters":{"category":category,"start_date":start_date,"end_date":end_date},"results":items,"count":len(items),"execution_time_ms":int(elapsed)}

def keyword(table, keyword, limit=20):
    gpk = f"KEYWORD#{keyword}"
    start = time.time()
    resp = table.query(IndexName='KeywordIndex', KeyConditionExpression=Key('GSI3PK').eq(gpk), Limit=limit, ScanIndexForward=False)
    elapsed = (time.time() - start) * 1000.0
    items = resp.get('Items', [])
    return {"query_type":"papers_by_keyword","parameters":{"keyword":keyword,"limit":limit},"results":items,"count":len(items),"execution_time_ms":int(elapsed)}

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('recent'); p.add_argument('category'); p.add_argument('--limit', type=int, default=20); p.add_argument('--table', default='arxiv-papers'); p.add_argument('--region', default='us-west-2')
    p = sub.add_parser('author'); p.add_argument('author_name'); p.add_argument('--table', default='arxiv-papers'); p.add_argument('--region', default='us-west-2')
    p = sub.add_parser('get'); p.add_argument('arxiv_id'); p.add_argument('--table', default='arxiv-papers'); p.add_argument('--region', default='us-west-2')
    p = sub.add_parser('daterange'); p.add_argument('category'); p.add_argument('start_date'); p.add_argument('end_date'); p.add_argument('--table', default='arxiv-papers'); p.add_argument('--region', default='us-west-2')
    p = sub.add_parser('keyword'); p.add_argument('keyword'); p.add_argument('--limit', type=int, default=20); p.add_argument('--table', default='arxiv-papers'); p.add_argument('--region', default='us-west-2')

    args = parser.parse_args()
    table = table_resource(args.region, getattr(args, 'table'))

    if args.cmd == 'recent':
        out = recent(table, args.category, args.limit)
    elif args.cmd == 'author':
        out = author(table, args.author_name)
    elif args.cmd == 'get':
        out = get_paper(table, args.arxiv_id)
    elif args.cmd == 'daterange':
        out = daterange(table, args.category, args.start_date, args.end_date)
    elif args.cmd == 'keyword':
        out = keyword(table, args.keyword, args.limit)
    else:
        out = {"error":"unknown command"}

    print(json.dumps(out, default=str, indent=2))

if __name__ == '__main__':
    main()