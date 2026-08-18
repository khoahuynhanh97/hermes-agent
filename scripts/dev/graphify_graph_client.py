"""Graphify graph client helper to query and explain nodes directly from the graph JSON."""
import json
import sys
from pathlib import Path

def load_graph(graph_file: Path) -> dict:
    if not graph_file.exists():
        print(f"Graph file not found at: {graph_file}")
        sys.exit(1)
    with open(graph_file, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    if len(sys.argv) < 4:
        print("Usage: graphify_graph_client.py <command> <graph_file> <args...>")
        sys.exit(1)

    command = sys.argv[1]
    graph_file = Path(sys.argv[2])
    cmd_args = sys.argv[3:]

    graph_data = load_graph(graph_file)
    nodes = graph_data.get("nodes", [])
    links = graph_data.get("links", [])

    if command == "query":
        query_string = " ".join(cmd_args).lower()
        print(f"Graph loaded: {len(nodes)} nodes across knowledge communities.")
        
        matches = []
        for n in nodes:
            nid = str(n.get("id", "")).lower()
            label = str(n.get("label", "")).lower()
            sf = str(n.get("source_file", "")).lower()
            comm = str(n.get("community_name", "")).lower()
            
            if (query_string in nid or 
                query_string in label or 
                query_string in sf or 
                query_string in comm):
                matches.append(n)
                
        # Limit to top 10 matches
        top_matches = matches[:10]
        print(f"Matched {len(matches)} nodes (showing top {len(top_matches)}):")
        for n in top_matches:
            loc = f" at {n['source_location']}" if n.get("source_location") else ""
            print(f"- Node: {n.get('id')}")
            print(f"  Label: {n.get('label')}")
            print(f"  Source File: {n.get('source_file')}{loc}")
            print(f"  Community: {n.get('community_name')} (ID: {n.get('community')})")

    elif command == "explain":
        target = " ".join(cmd_args).lower()
        matched_node = None
        for n in nodes:
            nid = str(n.get("id", "")).lower()
            label = str(n.get("label", "")).lower()
            sf = str(n.get("source_file", "")).lower()
            if target == nid or target == label or target == sf or target in sf:
                matched_node = n
                break
                
        if not matched_node:
            print(f"Node '{target}' not found in the graph.")
            sys.exit(1)
            
        nid = matched_node.get("id")
        loc = f" at {matched_node['source_location']}" if matched_node.get("source_location") else ""
        print(f"NODE DETAILS:")
        print(f"  ID: {nid}")
        print(f"  Label: {matched_node.get('label')}")
        print(f"  File Type: {matched_node.get('file_type')}")
        print(f"  Source File: {matched_node.get('source_file')}{loc}")
        print(f"  Community: {matched_node.get('community_name')} (ID: {matched_node.get('community')})")
        print(f"  Metadata: {matched_node.get('metadata')}")
        
        # Find inbound and outbound connections
        out_edges = []
        in_edges = []
        for l in links:
            src = l.get("source")
            tgt = l.get("target")
            rel = l.get("relation", "connected_to")
            if src == nid:
                out_edges.append((rel, tgt))
            elif tgt == nid:
                in_edges.append((rel, src))
                
        if out_edges:
            print("\nOUTBOUND EDGES:")
            for rel, tgt in out_edges[:15]:
                print(f"  --({rel})--> {tgt}")
            if len(out_edges) > 15:
                print(f"  ... ({len(out_edges) - 15} more outbound edges)")
                
        if in_edges:
            print("\nINBOUND EDGES:")
            for rel, src in in_edges[:15]:
                print(f"  <--({rel})-- {src}")
            if len(in_edges) > 15:
                print(f"  ... ({len(in_edges) - 15} more inbound edges)")

    elif command == "list_paths":
        seen_paths = set()
        paths = []
        for n in nodes:
            sf = n.get("source_file")
            if sf and sf not in seen_paths:
                seen_paths.add(sf)
                paths.append(sf)
        print(json.dumps(paths))

if __name__ == "__main__":
    main()
