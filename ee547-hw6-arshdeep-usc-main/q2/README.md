## API Gateway base URL:
`https://52c3s38dh8.execute-api.us-west-2.amazonaws.com`

## DynamoDB:
- Table name: `earthquakes`
- Partition key: PK = `EQ`
- Sort key: SK = `<time_iso>#<earthquake_id>`
- GSIs:
  - GSI name: `earthquake_id-index`
  - GSI partition key: `earthquake_id`
  - Projection: ALL
- Justification
  - The fixed partition key `EQ` keeps all earthquake records in one logical collection.
  - The sort key begins with an ISO-8601 timestamp, so items sort lexicographically by time.
  - The earthquake ID is included in the sort key so records remain unique even when multiple earthquakes occur at the same second.
  - The Query Lambda can retrieve a date range by querying `PK = EQ` and `SK BETWEEN start AND end`, then return the newest events first by sorting descending.

## Data flow:
1. `fetch` runs on an EventBridge schedule every 10 minutes.
2. It calls the public USGS GeoJSON feed and writes the raw response to S3 in `raw/`.
3. `process` is triggered by `S3:ObjectCreated` events for the `raw/` prefix.
4. It reads the GeoJSON, validates each feature, converts it into a flat record, and writes it to DynamoDB table `earthquakes`.
5. `query` is triggered by API Gateway requests and reads from `earthquakes` to return a JSON response.

## Duplication avoidance:
The overlap does not create duplicate records because the `process` Lambda writes each item using the same DynamoDB key for the same USGS event ID and timestamp combination. Re-processing the same event overwrites the existing item instead of creating a new one.
