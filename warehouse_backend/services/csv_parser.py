import csv
import io


def parse_warehouse(content: str) -> list[dict]:
    """No header. Columns: coordX, coordY. Coords can be negative (Case3)."""
    rows = []
    for row in csv.reader(io.StringIO(content.strip())):
        if len(row) >= 2:
            rows.append({"x": int(row[0].strip()), "y": int(row[1].strip())})
    return rows


def parse_obstacles(content: str) -> list[dict]:
    """No header. Columns: coordX, coordY, width, depth. File may be empty (Case1)."""
    rows = []
    for row in csv.reader(io.StringIO(content.strip())):
        if len(row) >= 4:
            rows.append({
                "x": int(row[0].strip()),
                "y": int(row[1].strip()),
                "width": int(row[2].strip()),
                "depth": int(row[3].strip()),
            })
    return rows  # returns [] for empty file — valid


def parse_ceiling(content: str) -> list[dict]:
    """No header. Columns: coordX, ceilingHeight. coordX can be negative (Case3: -7500)."""
    rows = []
    for row in csv.reader(io.StringIO(content.strip())):
        if len(row) >= 2:
            rows.append({"xFrom": int(row[0].strip()), "maxHeight": int(row[1].strip())})
    return sorted(rows, key=lambda s: s["xFrom"])  # always sort ascending


def parse_bay_catalog(content: str) -> list[dict]:
    """No header. Columns: typeId, width, depth, height, gap, nLoads, price."""
    rows = []
    for row in csv.reader(io.StringIO(content.strip())):
        if len(row) >= 7:
            rows.append({
                "typeId": int(row[0].strip()),
                "width": int(row[1].strip()),
                "depth": int(row[2].strip()),
                "height": int(row[3].strip()),
                "gap": int(row[4].strip()),
                "nLoads": int(row[5].strip()),
                "price": int(row[6].strip()),
            })
    return rows
