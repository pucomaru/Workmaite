# Neo4j Project

This project sets up a Neo4j database using Docker. It includes configuration files, initialization scripts, and seeding scripts to help you get started with your Neo4j database.

## Project Structure

```
neo4j-project
├── docker
│   └── neo4j.conf
├── scripts
│   ├── init.cypher
│   └── seed.cypher
├── docker-compose.yml
├── .env
└── README.md
```

## Getting Started

### Prerequisites

- Docker installed on your machine.
- Docker Compose installed.

### Setup Instructions

1. Clone this repository to your local machine.
2. Navigate to the project directory:
   ```
   cd neo4j-project
   ```
3. Create a `.env` file with your Neo4j credentials:
   ```
   NEO4J_AUTH=neo4j/password
   NEO4J_DB=your_database_name
   ```
4. Start the Neo4j database using Docker Compose:
   ```
   docker-compose up -d
   ```

### Database Initialization

- The `scripts/init.cypher` file contains the Cypher queries to set up the database schema. You can run this script after starting the database to create the necessary node labels and relationships.
  
### Seeding Data

- Use the `scripts/seed.cypher` file to populate your database with initial data. This script should be executed after the initialization script.

### Accessing Neo4j
- portforward
```
kubectl port-forward -n skala3-finalproj-class2-team9 svc/workmaite-neo4j 7474:7474 7687:7687
``` 
- Once the database is running, you can access the Neo4j browser at `http://localhost:7474` using the credentials specified in the `.env` file.

## Usage Examples

- After setting up your database, you can run Cypher queries directly in the Neo4j browser or through your application code.

## License

This project is licensed under the MIT License.