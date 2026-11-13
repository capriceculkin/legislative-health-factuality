# dbpedia_test.py
# Tests the DBpedia SPARQL endpoint with health-related queries to understand
# what factual information is queryable and how to structure claims for
# verification against the knowledge graph.
# This is the first step toward the factuality scoring pipeline described
# in the July 6 meeting with David Chartash and Joanie Bouchard.

import requests
import json

SPARQL_ENDPOINT = "https://dbpedia.org/sparql"

def query_dbpedia(sparql_query):
    params = {
        "query": sparql_query,
        "format": "application/json"
    }
    resp = requests.get(
        SPARQL_ENDPOINT,
        params=params,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15
    )
    if resp.status_code != 200:
        print(f"Error {resp.status_code}: {resp.text[:200]}")
        return None
    return resp.json()

if __name__ == "__main__":

    # Test 1: what does DBpedia know about Medicare
    print("=== Test 1: Medicare facts ===")
    q1 = """
    PREFIX dbo: <http://dbpedia.org/ontology/>
    PREFIX dbr: <http://dbpedia.org/resource/>
    SELECT ?predicate ?object WHERE {
        <http://dbpedia.org/resource/Medicare_(United_States)> ?predicate ?object .
    } LIMIT 10
    """
    results = query_dbpedia(q1)
    if results:
        for r in results["results"]["bindings"]:
            pred = r["predicate"]["value"].split("/")[-1]
            obj = r["object"]["value"]
            print(f"  {pred}: {obj[:80]}")

    # Test 2: what does DBpedia know about smoking and disease
    print("\n=== Test 2: Smoking and disease ===")
    q2 = """
    SELECT ?disease WHERE {
        dbr:Tobacco_smoking dbo:disease ?disease .
    } LIMIT 10
    """
    results = query_dbpedia(q2)
    for r in results["results"]["bindings"]:
        print(f"  {r['disease']['value']}")

    # Test 3: health-related entities in DBpedia
    print("\n=== Test 3: Sample health entities ===")
    q3 = """
    SELECT ?entity ?label WHERE {
        ?entity a dbo:Disease .
        ?entity rdfs:label ?label .
        FILTER(LANG(?label) = 'en')
    } LIMIT 10
    """

    results = query_dbpedia(q3)
    for r in results["results"]["bindings"]:
        print(f"  {r['label']['value']}")

    # Test 4: Canada Health Act facts
    q4 = """
    PREFIX dbo: <http://dbpedia.org/ontology/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?predicate ?object WHERE {
        <http://dbpedia.org/resource/Canada_Health_Act> ?predicate ?object .
    } LIMIT 20
    """

    print("\n=== Test 4: Canada Health Act ===")
    results4 = query_dbpedia(q4)
    if results4:
        for r in results4["results"]["bindings"]:
            pred = r["predicate"]["value"].split("/")[-1]
            obj = r["object"]["value"][:200]
            print(f"  {pred}: {obj}")
    else:
        print("  No results")

    results = query_dbpedia(q4)
    for r in results["results"]["bindings"]:
        print(f"  {r['label']['value']}")