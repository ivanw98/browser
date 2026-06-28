from browser import URL


def show(body: str, view_source: bool = False):
    if view_source:
        print(body)
        return
    in_tag = False
    in_entity = False
    entity = ""
    for c in body:
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            if c == "&":
                in_entity = True
                entity = ""
            elif in_entity:
                if c == ";":
                    in_entity = False
                    if entity == "lt":
                        print("<", end="")
                    elif entity == "gt":
                        print(">", end="")
                    else:
                        print(f"&{entity};", end="")  # unknown entity, print as-is
                else:
                    entity += c
            else:
                print(c, end="")


def load(url: URL):
    body = url.request()
    show(body=body, view_source=url.view_source)


if __name__ == "__main__":
    import sys

    load(URL(sys.argv[1]))
