"""Historical contract checks. These deliberately do not certify behavior."""

from . import __version__


WIRE = {"int": "i", "uint": "u", "fixed": "f", "string": "s",
        "object": "o", "new_id": "n", "array": "a", "fd": "h"}


def signature(message):
    """Return libwayland-style expanded wire signature, including since."""
    result = str(message["since"]) if message["since"] > 1 else ""
    for arg in message["args"]:
        if arg["type"] == "new_id" and not arg["interface"]:
            result += "su"
        if arg["allow_null"]:
            result += "?"
        result += WIRE[arg["type"]]
    return result


def compare_snapshots(old, new):
    """Compare validated snapshots. All findings are deterministic and complete."""
    findings = []

    def add(severity, code, path, before, after, message):
        findings.append(dict(severity=severity, code=code, path=path,
                             old=before, new=after, message=message))

    def change(severity, code, path, before, after, message):
        if before != after:
            add(severity, code, path, before, after, message)

    def docs(path, before, after):
        change("review", "description_changed", path, before, after,
               "Normative prose or summary changed; review behavior manually.")

    for name in sorted(set(old["protocols"]) | set(new["protocols"])):
        if name in old["protocols"] and name in new["protocols"]:
            docs("protocol/" + name, old["protocols"][name], new["protocols"][name])
        else:
            add("review", "protocol_identity_changed", "protocol/" + name,
                old["protocols"].get(name), new["protocols"].get(name),
                "Protocol container identity changed; verify the intended revision pair.")

    oi, ni = old["interfaces"], new["interfaces"]
    for name in sorted(oi):
        path = "interface/" + name
        before = oi[name]
        if name not in ni:
            add("break", "interface_removed", path, before["version"], None,
                "An existing interface disappeared; preserve it or use a new major identity.")
            continue
        after = ni[name]
        change("review", "protocol_membership_changed", path,
               before.get("protocol"), after.get("protocol"),
               "The interface moved between protocol containers; review code-generation dependencies.")
        if after["version"] < before["version"]:
            add("break", "version_decreased", path, before["version"], after["version"],
                "The advertised interface version decreased.")
        elif after["version"] > before["version"]:
            add("info", "version_increased", path, before["version"], after["version"],
                "Version increased; this does not repair changes at existing opcodes.")
        if before["frozen"] and not after["frozen"]:
            add("review", "frozen_removed", path, True, False,
                "The promise to keep this interface frozen at version 1 was removed.")
        docs(path, before["description"], after["description"])
        for direction in ("requests", "events"):
            bm, am = before[direction], after[direction]
            new_names = {m["name"]: m["opcode"] for m in am}
            for b in bm:
                mpath = path + "/" + direction[:-1] + "/" + str(b["opcode"]) + ":" + b["name"]
                if b["opcode"] >= len(am):
                    add("break", "message_removed", mpath, b, None,
                        "An existing opcode disappeared, even if it was deprecated.")
                    continue
                a = am[b["opcode"]]
                if b["name"] != a["name"]:
                    if b["name"] in new_names:
                        add("break", "opcode_shifted", mpath, b["name"], a["name"],
                            "The old message moved to another opcode; appending is required.")
                    else:
                        add("review", "message_renamed_or_replaced", mpath,
                            b["name"], a["name"],
                            "Wire position is retained but identity changed; generated API and behavior need review.")
                change("break", "message_since_changed", mpath, b["since"], a["since"],
                       "Availability of an existing opcode changed.")
                change("break", "wire_signature_changed", mpath, signature(b), signature(a),
                       "Expanded wire argument layout changed (generic new_id includes string and uint).")
                change("break", "destructor_changed", mpath, b["destructor"], a["destructor"],
                       "Object lifetime semantics changed at an existing opcode.")
                change("review", "deprecation_changed", mpath,
                       b["deprecated_since"], a["deprecated_since"],
                       "Deprecation is informational and does not permit removal.")
                docs(mpath, b["description"], a["description"])
                for index, (ba, aa) in enumerate(zip(b["args"], a["args"])):
                    apath = mpath + "/arg/" + str(index)
                    change("break", "argument_type_changed", apath, ba["type"], aa["type"],
                           "The declared argument type changed, including its generated API type.")
                    change("break", "argument_interface_changed", apath,
                           ba["interface"], aa["interface"],
                           "The target object interface or code-generation dependency changed.")
                    change("break", "nullability_changed", apath, ba["allow_null"], aa["allow_null"],
                           "The allowed null contract changed; direction-specific safety requires human review.")
                    change("review", "argument_name_changed", apath, ba["name"], aa["name"],
                           "Argument naming changed; named-argument bindings may be affected.")
                    change("review", "enum_annotation_changed", apath, ba["enum"], aa["enum"],
                           "Enum annotation changed; annotations do not automatically restrict wire values.")
                    docs(apath, ba["description"], aa["description"])
            for a in am[len(bm):]:
                mpath = path + "/" + direction[:-1] + "/" + str(a["opcode"]) + ":" + a["name"]
                if a["since"] <= before["version"]:
                    add("break", "unversioned_message", mpath, before["version"], a,
                        "A new opcode must be gated above the previous interface maximum version.")
                else:
                    add("review", "message_added", mpath, None, a,
                        "Version-gated append; review behavior and implementation support.")
                if before["frozen"]:
                    add("break", "frozen_extended", mpath, True, a,
                        "A frozen interface cannot gain messages.")
        be, ae = before["enums"], after["enums"]
        for ename in sorted(be):
            epath = path + "/enum/" + ename
            b = be[ename]
            if ename not in ae:
                add("break", "enum_removed", epath, b, None,
                    "An enum used by generated APIs disappeared.")
                continue
            a = ae[ename]
            change("break", "enum_since_changed", epath, b["since"], a["since"],
                   "Availability of the existing enumeration changed.")
            change("break", "bitfield_changed", epath, b["bitfield"], a["bitfield"],
                   "Integer/bitfield interpretation changed.")
            docs(epath, b["description"], a["description"])
            for entry in sorted(b["entries"]):
                vpath = epath + "/entry/" + entry
                bv, av = b["entries"][entry], a["entries"].get(entry)
                if av is None:
                    add("break", "enum_entry_removed", vpath, bv, None,
                        "An existing named enum entry disappeared.")
                    continue
                for field, code in (("value", "enum_value_changed"), ("since", "entry_since_changed")):
                    change("break", code, vpath, bv[field], av[field],
                           "An existing numeric enum contract changed.")
                change("review", "deprecation_changed", vpath,
                       bv["deprecated_since"], av["deprecated_since"],
                       "Entry deprecation changed; retain existing values.")
                docs(vpath, bv["description"], av["description"])
            for entry in sorted(set(a["entries"]) - set(b["entries"])):
                av = a["entries"][entry]
                add("review", "enum_entry_added", epath + "/entry/" + entry, None, av,
                    "New enum value; review the protocol's rules for unknown values and version gating.")
        for ename in sorted(set(ae) - set(be)):
            add("review", "enum_added", path + "/enum/" + ename, None, ae[ename],
                "New enum/API annotations require semantic review.")
        # Version propagation can be checked only for constructor targets supplied
        # in the input set. Runtime ownership and registry globals are not inferred.
        for direction in ("requests", "events"):
            for m in before[direction]:
                for arg in m["args"]:
                    child = arg["interface"]
                    if arg["type"] == "new_id" and child in oi and child in ni:
                        if (ni[child]["version"] > oi[child]["version"]
                                and (after["version"] <= before["version"]
                                     or after["version"] < ni[child]["version"])):
                            add("break", "constructor_version_not_propagated", path,
                                before["version"], ni[child]["version"],
                                "Supplied constructor target " + child + " increased version without its parent increasing.")
    for name in sorted(set(ni) - set(oi)):
        add("review", "interface_added", "interface/" + name, None, ni[name],
            "New interface; verify advertised globals, constructor hierarchy and dependencies manually.")

    # Report the external contracts explicitly even when unchanged, so a clean
    # structural result cannot be mistaken for checking definitions not supplied.
    external = set()
    for snapshot in (old, new):
        for interface in snapshot["interfaces"].values():
            for direction in ("requests", "events"):
                for message in interface[direction]:
                    for arg in message["args"]:
                        if arg["interface"] and arg["interface"] not in snapshot["interfaces"]:
                            external.add(arg["interface"])
                        if arg["enum"] and "." in arg["enum"]:
                            target = arg["enum"].split(".")[0]
                            if target not in snapshot["interfaces"]:
                                external.add(target)
    findings.sort(key=lambda f: (f["path"], f["code"], str(f["old"]), str(f["new"])))
    verdict = ("incompatible" if any(f["severity"] == "break" for f in findings)
               else "needs_review" if any(f["severity"] == "review" for f in findings)
               else "no_structural_hazards")
    return {"schema_version": 1, "tool_version": __version__, "verdict": verdict,
            "old": {"sources": old["sources"]}, "new": {"sources": new["sources"]},
            "findings": findings,
            "limits": {"behavior_certified": False,
                       "external_interfaces_not_checked": sorted(external),
                       "statement": "Only supplied XML declarations are compared. Unchanged prose is not proven correct; runtime behavior, external definitions, generated language ABI and advertised globals require human/native-tool review."}}
