#!/bin/bash

# Load .env if it exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

if [ "$ARANGO_MODE" == "REMOTE" ]; then
  DB="${ARANGO_DATABASE:-ic-knowledge-graph}"
  PASS="${ARANGO_PASSWORD:-}"
  USER="${ARANGO_USERNAME:-root}"
else
  DB="${LOCAL_ARANGO_DATABASE:-ic-knowledge-graph}"
  PASS="${LOCAL_ARANGO_PASSWORD:-}"
  USER="${LOCAL_ARANGO_USERNAME:-root}"
fi

# Drop incorrect collections
echo "Dropping edge collections..."
docker exec or1200-arango arangosh --server.database "$DB" --server.username "$USER" --server.password "$PASS" --javascript.execute-string "
try { db._drop('CONTAINS'); } catch(e) {}
try { db._drop('HAS_PORT'); } catch(e) {}
try { db._drop('MODIFIED'); } catch(e) {}
try { db._drop('DOCUMENTED_BY'); } catch(e) {}
"

edges=( "HAS_PORT" "CONTAINS" "MODIFIED" "DOCUMENTED_BY" )

for col in "${edges[@]}"
do
   echo "Importing Edge Collection $col..."
   docker exec or1200-arango arangoimport --server.database "$DB" --server.username "$USER" --server.password "$PASS" --collection "$col" --create-collection true --create-collection-type edge --file "/data/import_$col.json" --type json
done
