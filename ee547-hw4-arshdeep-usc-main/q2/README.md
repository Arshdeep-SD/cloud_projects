## Schema Design Decisions

### Why did you choose your partition key structure?

The schema is designed around **access patterns**, not normalization.  
Each primary access pattern is modeled directly into the key structure using a composite key:

- **PK (Partition Key)** = entity type + identifier  
  - `CATEGORY#<category>`
  - `AUTHOR#<author_name>`
  - `ARXIV#<arxiv_id>`
  - `KEYWORD#<keyword>`

- **SK (Sort Key)** = `<YYYY-MM-DD>#<arxiv_id>`

This structure enables:

- Efficient querying by category sorted by date
- Efficient querying by author
- Efficient querying by keyword
- Direct lookup by arXiv ID

The sort key embeds the publication date first, allowing lexicographic ordering for:
- Recent papers
- Date range queries within a category

This approach follows DynamoDB best practices:
> Model for queries, not for relationships.

---

### How many GSIs did you create and why?

We created **3 Global Secondary Indexes (GSIs):**

1. **AuthorIndex**
   - GSI1PK = `AUTHOR#<author>`
   - GSI1SK = `<date>#<arxiv_id>`
   - Enables efficient querying of papers by author.

2. **PaperIdIndex**
   - GSI2PK = `ARXIV#<arxiv_id>`
   - GSI2SK = `META#<arxiv_id>`
   - Enables direct lookup of a paper by ID.

3. **KeywordIndex**
   - GSI3PK = `KEYWORD#<keyword>`
   - GSI3SK = `<date>#<arxiv_id>`
   - Enables querying papers by extracted abstract keywords.

Each GSI corresponds directly to a required access pattern.

---

### What denormalization trade-offs did you make?

Instead of storing one paper record and joining related data (as in relational databases), we:

- Created **multiple DynamoDB items per paper**
- Duplicated common metadata (`title`, `authors`, `categories`, etc.)
- Stored separate items for:
  - Categories
  - Authors
  - Keywords
  - Canonical paper metadata

This increases storage but dramatically improves query performance by eliminating joins.

Trade-off:
- Increased storage and write cost
- Harder updates (must update multiple items)

---

## Denormalization Analysis

### Average Number of DynamoDB Items Per Paper

For each paper, we create:

- 1 item per category
- 1 item per author
- ~10 items per keyword (default `top_keywords=10`)
- 1 canonical metadata item

Average estimate:

- ~2 categories
- ~3 authors
- 10 keywords
- 1 ID item

**≈ 16 items per paper**

---

### Storage Multiplication Factor

Since each paper is stored ~16 times on average:

**Storage multiplication factor ≈ 16×**

Compared to a normalized relational model (1 row per paper), this is a significant increase.

---

### Which access patterns caused the most duplication?

The largest duplication comes from:

1. **Keyword indexing** (top N keywords per paper)
2. **Author indexing** (one item per author)

Keywords cause the highest duplication because:
- Each paper generates multiple keyword items
- Keywords are derived from abstract content

---

## Query Limitations

### What queries are NOT efficiently supported?

Examples:

- Count total papers by author
- Most cited papers globally
- Top authors by number of papers
- Aggregations across all categories
- Full-text search in abstract
- Global sorting across partitions

---

### Why are these difficult in DynamoDB?

DynamoDB limitations:

1. **No joins**
2. **No GROUP BY**
3. **No aggregation queries**
4. **No global secondary sorting across partitions**
5. **No built-in full-text search**

To compute:
> “Count total papers by author”

We must:
- Query all author items
- Count client-side

To compute:
> “Most cited papers globally”

We would need:
- A separate precomputed counter
- Or a scan across the entire table (inefficient)

DynamoDB excels at:
- Key-based lookups
- Predefined access patterns

It performs poorly for:
- Ad-hoc analytical queries
- Complex aggregations

---

## When to Use DynamoDB

### When would you choose DynamoDB over PostgreSQL?

Choose DynamoDB when:

- have **predictable access patterns**
- need **low-latency reads at scale**
- need **horizontal scalability**
- building the following:
  - Event-driven systems
  - Microservices
  - High-read APIs
  - Serverless architectures

---

### When would you choose PostgreSQL instead?

Choose PostgreSQL when:

- need complex joins
- need flexible querying
- require aggregations (COUNT, SUM, GROUP BY)
- need ACID transactions across many entities
- expect evolving, ad-hoc query requirements

---

## Key Trade-Offs

| Feature | DynamoDB | PostgreSQL |
|----------|------------|--------------|
| Schema Flexibility | Low (query-driven) | High |
| Joins | No | Yes |
| Aggregations | Limited | Powerful |
| Scalability | Excellent (automatic) | Manual scaling |
| Latency | Very low | Moderate |
| Storage Efficiency | Lower (denormalized) | Higher (normalized) |
| Operational Complexity | Low | Higher |

