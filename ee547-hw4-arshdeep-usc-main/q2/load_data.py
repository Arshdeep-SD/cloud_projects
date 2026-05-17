# q2/load_data.py
import argparse
import json
import re
import time
from collections import Counter
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeSerializer
from stopwords import STOPWORDS

# Helpers
def normalize_token(t):
    t = t.lower()
    # keep alphanum and dashes/underscore
    t = re.sub(r"[^a-z0-9_\-]", "", t)
    return t

def extract_keywords(text, top_n=10):
    if not text:
        return []
    tokens = re.findall(r"[A-Za-z0-9_\-']+", text.lower())
    tokens = [normalize_token(t) for t in tokens if t]
    tokens = [t for t in tokens if t and t not in STOPWORDS and len(t) > 2]
    c = Counter(tokens)
    most = [w for w,_ in c.most_common(top_n)]
    return most

def ensure_table(client, table_name):
    # create table if not exists with required attribute defs and GSIs
    try:
        resp = client.describe_table(TableName=table_name)
        print(f"Table {table_name} already exists. Skipping create.")
        return
    except ClientError as e:
        if e.response['Error']['Code'] != 'ResourceNotFoundException':
            raise

    print(f"Creating table {table_name} ...")
    client.create_table(
        TableName=table_name,
        AttributeDefinitions=[
            {"AttributeName":"PK","AttributeType":"S"},
            {"AttributeName":"SK","AttributeType":"S"},
            {"AttributeName":"GSI1PK","AttributeType":"S"},
            {"AttributeName":"GSI1SK","AttributeType":"S"},
            {"AttributeName":"GSI2PK","AttributeType":"S"},
            {"AttributeName":"GSI2SK","AttributeType":"S"},
            {"AttributeName":"GSI3PK","AttributeType":"S"},
            {"AttributeName":"GSI3SK","AttributeType":"S"},
        ],
        KeySchema=[
            {"AttributeName":"PK","KeyType":"HASH"},
            {"AttributeName":"SK","KeyType":"RANGE"}
        ],
        BillingMode="PAY_PER_REQUEST",
        GlobalSecondaryIndexes=[
            {
                "IndexName":"AuthorIndex",
                "KeySchema":[{"AttributeName":"GSI1PK","KeyType":"HASH"},{"AttributeName":"GSI1SK","KeyType":"RANGE"}],
                "Projection":{"ProjectionType":"ALL"}
            },
            {
                "IndexName":"PaperIdIndex",
                "KeySchema":[{"AttributeName":"GSI2PK","KeyType":"HASH"},{"AttributeName":"GSI2SK","KeyType":"RANGE"}],
                "Projection":{"ProjectionType":"ALL"}
            },
            {
                "IndexName":"KeywordIndex",
                "KeySchema":[{"AttributeName":"GSI3PK","KeyType":"HASH"},{"AttributeName":"GSI3SK","KeyType":"RANGE"}],
                "Projection":{"ProjectionType":"ALL"}
            }
        ]
    )
    print("Waiting for table to become ACTIVE...")
    waiter = client.get_waiter('table_exists')
    waiter.wait(TableName=table_name)
    print("Table active.")

def make_item(pk, sk, body):
    item = {"PK": pk, "SK": sk}
    item.update(body)
    return item

def to_dynamo(item):
    # convert python object to Dynamo items using TypeSerializer
    ts = TypeSerializer()
    return {k: ts.serialize(v) for k,v in item.items()}

def batch_write_table(table, items):
    written = 0
    with table.batch_writer() as batch:
        for it in items:
            batch.put_item(Item=it)
            written += 1
    return written

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('papers_json', help='path to papers.json')
    parser.add_argument('table_name', help='dynamo table name')
    parser.add_argument('--region', default='us-west-2')
    parser.add_argument('--top_keywords', type=int, default=10)
    args = parser.parse_args()

    with open(args.papers_json, 'r', encoding='utf-8') as f:
        papers = json.load(f)

    client = boto3.client('dynamodb', region_name=args.region)
    dynamo = boto3.resource('dynamodb', region_name=args.region)
    ensure_table(client, args.table_name)
    table = dynamo.Table(args.table_name)

    all_items = []
    stats = {
        'papers': 0,
        'category_items': 0,
        'author_items': 0,
        'keyword_items': 0,
        'id_items': 0
    }

    print("Processing papers...")
    for p in papers:
        stats['papers'] += 1
        arxiv_id = p.get('arxiv_id')
        title = p.get('title')
        authors = p.get('authors', [])
        abstract = p.get('abstract', '') or ''
        published = p.get('published', p.get('updated', '1970-01-01T00:00:00Z'))
        pubdate = published[:10]
        categories = p.get('categories', [])
        if isinstance(categories, str):
            categories = [categories]

        keywords = extract_keywords(abstract, top_n=args.top_keywords)

        body_common = {
            'arxiv_id': arxiv_id,
            'title': title,
            'authors': authors,
            'published': published,
            'categories': categories,
        }

        # category items
        for cat in categories:
            pk = f"CATEGORY#{cat}"
            sk = f"{pubdate}#{arxiv_id}"
            item = make_item(pk, sk, {**body_common, 'type': 'category_item'})
            all_items.append(item)
            stats['category_items'] += 1

        # author items (create one per author). Also set GSI1 attrs for query convenience.
        for a in authors:
            pk = f"AUTHOR#{a}"
            sk = f"{pubdate}#{arxiv_id}"
            item = make_item(pk, sk, {**body_common, 'type': 'author_item', 'GSI1PK': pk, 'GSI1SK': sk})
            all_items.append(item)
            stats['author_items'] += 1

        # keyword items
        for kw in keywords:
            gpk = f"KEYWORD#{kw}"
            gsk = f"{pubdate}#{arxiv_id}"
            item = make_item(gpk, gsk, {**body_common, 'type': 'keyword_item', 'keyword': kw, 'GSI3PK': gpk, 'GSI3SK': gsk})
            all_items.append(item)
            stats['keyword_items'] += 1

        # canonical paper id item (direct lookup)
        g2pk = f"ARXIV#{arxiv_id}"
        g2sk = f"META#{arxiv_id}"
        item = make_item(g2pk, g2sk, {**body_common, 'type': 'paper_item', 'abstract': abstract, 'keywords': keywords, 'GSI2PK': g2pk, 'GSI2SK': g2sk})
        all_items.append(item)
        stats['id_items'] += 1

    print(f"Prepared {len(all_items)} DynamoDB items for {stats['papers']} papers.")
    # Batch write (Table.batch_writer handles chunking/retries)
    print("Writing items to DynamoDB (this may take a moment)...")
    start = time.time()
    written = batch_write_table(table, all_items)
    elapsed = time.time() - start
    total_items = written
    denorm_factor = total_items / max(1, stats['papers'])
    print(f"Write completed in {elapsed:.1f}s — {written} items written.")
    print()
    print("Load summary:")
    print(f"  Papers loaded: {stats['papers']}")
    print(f"  Category items: {stats['category_items']}")
    print(f"  Author items: {stats['author_items']}")
    print(f"  Keyword items: {stats['keyword_items']}")
    print(f"  Paper ID items: {stats['id_items']}")
    print(f"  Total items: {total_items}")
    print(f"  Denormalization factor: {denorm_factor:.2f}x")

if __name__ == '__main__':
    main()