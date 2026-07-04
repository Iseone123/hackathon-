"""Neo4j knowledge graph store."""

from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase

from app.config import settings
from app.models import Entity


class Neo4jStore:
    NODE_TYPES = {"Material", "Process", "Property", "Parameter", "Publication"}
    REL_TYPES = {"AFFECTS", "USED_IN", "CITED_BY", "CORRELATES_WITH"}

    def __init__(self) -> None:
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        self._init_constraints()

    def close(self) -> None:
        self._driver.close()

    def _init_constraints(self) -> None:
        with self._driver.session() as session:
            for label in self.NODE_TYPES:
                session.run(
                    f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) "
                    f"REQUIRE n.name IS UNIQUE"
                )

    def upsert_publication(self, doc_id: str, metadata: dict[str, Any]) -> None:
        with self._driver.session() as session:
            session.run(
                """
                MERGE (p:Publication {id: $doc_id})
                SET p.title = $title, p.source = $source, p.date = $date
                """,
                doc_id=doc_id,
                title=metadata.get("title", doc_id),
                source=metadata.get("source", ""),
                date=metadata.get("date", ""),
            )

    def upsert_entities(
        self,
        doc_id: str,
        entities: list[Entity],
        relations: list[dict[str, Any]],
    ) -> None:
        with self._driver.session() as session:
            for entity in entities:
                label = entity.type if entity.type in self.NODE_TYPES else "Parameter"
                session.run(
                    f"""
                    MERGE (n:{label} {{name: $name}})
                    SET n += $props
                    WITH n
                    MATCH (p:Publication {{id: $doc_id}})
                    MERGE (p)-[:CITED_BY]->(n)
                    """,
                    name=entity.name,
                    props=entity.properties,
                    doc_id=doc_id,
                )
            for rel in relations:
                rel_type = rel.get("type", "CORRELATES_WITH")
                if rel_type not in self.REL_TYPES:
                    rel_type = "CORRELATES_WITH"
                session.run(
                    f"""
                    MERGE (a {{name: $source}})
                    MERGE (b {{name: $target}})
                    MERGE (a)-[r:{rel_type}]->(b)
                    SET r.doc_id = $doc_id
                    """,
                    source=rel.get("source", ""),
                    target=rel.get("target", ""),
                    doc_id=doc_id,
                )

    def get_subgraph(self, keywords: list[str], limit: int = 30) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        links: list[dict[str, Any]] = []
        if not keywords:
            return {"nodes": nodes, "links": links}

        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n)
                WHERE ANY(kw IN $keywords WHERE toLower(n.name) CONTAINS toLower(kw))
                OPTIONAL MATCH (n)-[r]-(m)
                RETURN DISTINCT n, r, m
                LIMIT $limit
                """,
                keywords=keywords,
                limit=limit,
            )
            seen_nodes: set[str] = set()
            for record in result:
                for key in ("n", "m"):
                    node = record[key]
                    if node and node.element_id not in seen_nodes:
                        seen_nodes.add(node.element_id)
                        labels = list(node.labels)
                        nodes.append(
                            {
                                "id": node.get("name", node.element_id),
                                "type": labels[0] if labels else "Entity",
                                "properties": dict(node),
                            }
                        )
                rel = record["r"]
                if rel:
                    links.append(
                        {
                            "source": record["n"].get("name", ""),
                            "target": record["m"].get("name", "") if record["m"] else "",
                            "type": rel.type,
                        }
                    )
        return {"nodes": nodes, "links": links}

    def is_available(self) -> bool:
        try:
            with self._driver.session() as session:
                session.run("RETURN 1")
            return True
        except Exception:
            return False
