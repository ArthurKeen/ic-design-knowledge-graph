#!/bin/bash

# Load .env if it exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# Select target based on ARANGO_MODE
if [ "$ARANGO_MODE" == "REMOTE" ]; then
    DB_ENDPOINT="$ARANGO_ENDPOINT"
    DB_USER="$ARANGO_USERNAME"
    DB_PASS="$ARANGO_PASSWORD"
    DB="${ARANGO_DATABASE:-ic-knowledge-graph}"
    echo ">>>> MODE: REMOTE (AMP) <<<<"
else
    # default local docker endpoint as seen from the host is localhost:8530
    # but inside the container it's usually 127.0.0.1:8529
    DB_ENDPOINT="http://127.0.0.1:8529"
    DB_USER="root"
    DB_PASS=""
    DB="${LOCAL_ARANGO_DATABASE:-ic-knowledge-graph}"
    echo ">>>> MODE: LOCAL (Docker) <<<<"
fi

collections=( "RTL_Module" "RTL_Port" "RTL_Signal" "RTL_LogicChunk" "GitCommit" "FSM_StateMachine" "FSM_State" "RTL_Parameter" "RTL_Memory" "RTL_Function" "RTL_Assign" "RTL_Assertion" "RTL_Always" "ClockDomain" "BusInterface" "MemoryPort" "Operator" "GenerateBlock" )
edges=( "HAS_PORT" "HAS_SIGNAL" "CONTAINS" "MODIFIED" "WIRED_TO" "DEPENDS_ON" "HAS_FSM" "HAS_STATE" "TRANSITIONS_TO" "STATE_REGISTER" "IMPLEMENTED_BY" "HAS_PARAMETER" "USES_PARAMETER" "HAS_MEMORY" "MEMORY_PORT" "STORED_IN" "HAS_FUNCTION" "CALLS_FUNCTION" "FUNCTION_INPUT" "FUNCTION_OUTPUT" "HAS_ASSIGN" "DRIVES" "READS_FROM" "HAS_ASSERTION" "CHECKS_SIGNAL" "HAS_ALWAYS" "SENSITIVE_TO" "CLOCKED_BY" "RESET_BY" "CROSSES_DOMAIN" "PART_OF_BUS" "IMPLEMENTS" "OVERRIDES" "ACCESSES" "USES_OPERATOR" "CALLS" "HAS_OPERATOR" )

for col in "${collections[@]}"
do
   echo "Importing Document Collection: $col to $DB..."
   # Truncate before import to ensure fresh data
   docker exec or1200-arango arangosh \
     --server.endpoint "$DB_ENDPOINT" \
     --server.database "$DB" \
     --server.username "$DB_USER" \
     --server.password "$DB_PASS" \
     --javascript.execute-string "if(db.$col) db.$col.truncate();" --quiet

   docker exec or1200-arango arangoimport \
     --server.endpoint "$DB_ENDPOINT" \
     --server.database "$DB" \
     --server.username "$DB_USER" \
     --server.password "$DB_PASS" \
     --collection "$col" \
     --create-collection true \
     --create-collection-type document \
     --overwrite true \
     --file "/data/import_$col.json" \
     --type json
done

for col in "${edges[@]}"
do
   echo "Importing Edge Collection: $col to $DB..."
   # Note: To change collection type or clear it while in a graph, truncate is safer than drop
   docker exec or1200-arango arangosh \
     --server.endpoint "$DB_ENDPOINT" \
     --server.database "$DB" \
     --server.username "$DB_USER" \
     --server.password "$DB_PASS" \
     --javascript.execute-string "if(db.$col) db.$col.truncate();" --quiet

   docker exec or1200-arango arangoimport \
     --server.endpoint "$DB_ENDPOINT" \
     --server.database "$DB" \
     --server.username "$DB_USER" \
     --server.password "$DB_PASS" \
     --collection "$col" \
     --create-collection true \
     --create-collection-type edge \
     --overwrite true \
     --file "/data/import_$col.json" \
     --type json
done

echo "Import Complete."

# Run GraphRAG import (if configured)
if [ "$RUN_GRAPHRAG" = "true" ]; then
    echo ""
    echo "========================================"
    echo "Step 4: GraphRAG Document Import"
    echo "========================================"
    python src/etl_graphrag.py --import
fi
