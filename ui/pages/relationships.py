"""Interactive, read-only Neo4j relationship explorer."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

import importlib
import src.utils.graph_store as graph_store

graph_store = importlib.reload(graph_store)


st.set_page_config(page_title="Knowledge Graph", page_icon="🕸️", layout="wide")

LABEL_COLORS = {
    "PERSON": "#2563EB",
    "ORG": "#7C3AED",
    "PRODUCT": "#059669",
    "GPE": "#D97706",
    "LOC": "#EA580C",
    "LAW": "#DC2626",
    "DOCUMENT": "#F8FAFC",
    "SKILL": "#14B8A6",
    "EXPERIENCE": "#F59E0B",
    "ROLE": "#EC4899",
    "PROJECT": "#10B981",
    "FEATURE": "#06B6D4",
    "TASK": "#64748B",
    "Entity": "#475569",
}


def build_graph_html(snapshot: dict, height: int = 720) -> str:
    network = Network(
        height=f"{height}px",
        width="100%",
        bgcolor="#0F172A",
        font_color="#F8FAFC",
        directed=True,
        cdn_resources="in_line",
    )
    network.barnes_hut(gravity=-4500, central_gravity=0.25, spring_length=150)

    for node in snapshot["nodes"]:
        label = node.get("label") or "Entity"
        network.add_node(
            node["id"],
            label=node["id"],
            title=f"{node['id']} · {label}",
            color=LABEL_COLORS.get(label, "#475569"),
            shape="dot",
            size=18,
        )

    for edge in snapshot["relationships"]:
        network.add_edge(
            edge["source"],
            edge["target"],
            label=edge["relation"],
            title=f"{edge['source']} —[{edge['relation']}]→ {edge['target']}",
            color="#94A3B8",
            arrows="to",
        )

    network.set_options(
        """
        {
          "interaction": {"hover": true, "navigationButtons": true, "keyboard": true},
          "edges": {
            "font": {"size": 11, "color": "#CBD5E1", "strokeWidth": 0},
            "smooth": {"type": "dynamic"}
          },
          "nodes": {"font": {"size": 14, "face": "Arial"}},
          "physics": {"stabilization": {"iterations": 180}}
        }
        """
    )
    return network.generate_html()


st.title("Knowledge Graph Relationships")
st.caption("Explore the connected entities and relationships currently stored in Neo4j.")

if st.button("← Back to chat", use_container_width=False):
    st.switch_page("app.py")

labels = []
documents = []
try:
    labels = graph_store.get_entity_labels()
    documents = graph_store.get_graph_documents()
except Exception as exc:
    st.error(f"Could not connect to Neo4j: {exc}")
    st.stop()

with st.sidebar:
    st.header("Graph filters")
    search = st.text_input("Find entity or relationship", placeholder="e.g. OpenAI, WORKS_AT")
    selected_label = st.selectbox("Entity type", ["All"] + labels)
    doc_options = {"All": ""}
    doc_options.update({doc["name"]: doc["id"] for doc in documents})
    selected_document = st.selectbox("Document graph", list(doc_options.keys()))
    include_documents = st.checkbox("Show document source nodes", value=True)
    relationship_limit = st.slider("Maximum relationships", 100, 5000, 1000, step=100)
    st.caption("Large graphs are capped to keep the browser responsive.")

with st.spinner("Loading connected graph from Neo4j…"):
    snapshot = graph_store.get_graph_snapshot(
        limit=relationship_limit,
        search=search,
        entity_label="" if selected_label == "All" else selected_label,
        document_id=doc_options[selected_document],
        include_documents=include_documents,
    )

node_count = len(snapshot["nodes"])
edge_count = len(snapshot["relationships"])
col_nodes, col_edges, col_types = st.columns(3)
col_nodes.metric("Connected entities", node_count)
col_edges.metric("Relationships", edge_count)
col_types.metric(
    "Relationship types",
    len({edge["relation"] for edge in snapshot["relationships"]}),
)

if not snapshot["relationships"]:
    st.info("No connected relationships match these filters.")
else:
    components.html(build_graph_html(snapshot), height=750, scrolling=False)

    with st.expander("Relationship table", expanded=False):
        st.dataframe(
            snapshot["relationships"],
            use_container_width=True,
            hide_index=True,
            column_config={
                "source": "Source entity",
                "source_label": "Source type",
                "relation": "Relationship",
                "target": "Target entity",
                "target_label": "Target type",
            },
        )
