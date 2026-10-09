"""Graph questions about the network, using the NetworkX library.

Works with either storage (JSON file or Neo4j): we read the devices and links from
the knowledge base and build the graph in memory. No extra program to install.

    path(kb, "SW1", "SW3")          -> ["SW1", "R1", "R2", "R3", "SW3"]
    independent_paths(kb, "SW1", "SW3") -> 1  (2 or more = there is a backup path)
    impact(kb, "R2")                -> [["R1", "SW1"], ["R3", "SW3"]]  (the network splits)
    critical_devices(kb)            -> ["R1", "R2", "R3"]  (single points of failure)

Only the links in the knowledge base count (the data network, not the management cloud).
"""
import networkx as nx


def build_graph(kb) -> nx.Graph:
    graph = nx.Graph()
    for device in kb.list_devices():
        graph.add_node(device["name"])
    for link in kb.list_links():
        graph.add_edge(link["a"], link["b"])
    return graph


def path(kb, a: str, b: str) -> list[str]:
    """Shortest path from a to b (device names), or [] if there is none."""
    try:
        return nx.shortest_path(build_graph(kb), a, b)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def independent_paths(kb, a: str, b: str) -> int:
    """How many paths from a to b that share no link. 1 = no backup, 2+ = redundant."""
    graph = build_graph(kb)
    if a == b or a not in graph or b not in graph:
        return 0
    return nx.edge_connectivity(graph, a, b)


def impact(kb, device: str) -> list[list[str]]:
    """If `device` goes down, which groups of devices can no longer reach each other?
    Returns [] when nothing is cut off, else the separated groups."""
    graph = build_graph(kb)
    if device not in graph:
        return []
    neighbours_area = nx.node_connected_component(graph, device) - {device}
    graph.remove_node(device)
    groups = [sorted(g) for g in nx.connected_components(graph.subgraph(neighbours_area))]
    return sorted(groups) if len(groups) > 1 else []


def critical_devices(kb) -> list[str]:
    """Devices that split the network if they go down (single points of failure)."""
    return sorted(nx.articulation_points(build_graph(kb)))
