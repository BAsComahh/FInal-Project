"""Small English forms for explicit, manually supplied rule information."""

import math


class FieldDialog:
    """Pump Tk on the application thread without entering a nested event loop."""
    def __init__(self, title, fields, parse):
        import tkinter as tk
        from tkinter import ttk

        self.tk, self.parse = tk, parse
        self.result, self.done = None, False
        self.root = root = tk.Tk()
        root.title(title)
        root.attributes("-topmost", True)
        root.resizable(False, False)
        self.variables = {}
        for row, (key, label, value, kind) in enumerate(fields):
            ttk.Label(root, text=label).grid(row=row, column=0, padx=14, pady=7, sticky="w")
            variable = (tk.BooleanVar(master=root, value=bool(value)) if kind == "bool" else
                        tk.StringVar(master=root, value="" if value is None else str(value)))
            self.variables[key] = variable
            if kind == "bool":
                widget = ttk.Checkbutton(root, variable=variable)
            elif isinstance(kind, tuple):
                widget = ttk.Combobox(root, textvariable=variable, values=kind, state="readonly", width=28)
            else:
                widget = ttk.Entry(root, textvariable=variable, width=31)
            widget.grid(row=row, column=1, padx=14, pady=7, sticky="w")
        self.error = tk.StringVar(master=root, value="")
        ttk.Label(root, textvariable=self.error, foreground="firebrick", wraplength=430).grid(
            row=len(fields), column=0, columnspan=2, padx=14, sticky="w")
        ttk.Button(root, text="Save", command=self.save).grid(row=len(fields) + 1, column=0, padx=14, pady=14)
        ttk.Button(root, text="Cancel", command=self.close).grid(row=len(fields) + 1, column=1, padx=14, pady=14)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Escape>", lambda event: self.close())

    def save(self):
        try:
            self.result = self.parse({key: value.get() for key, value in self.variables.items()})
        except ValueError as error:
            self.error.set(str(error))
            return
        self.close()

    def poll(self):
        if not self.done:
            try:
                self.root.update_idletasks()
                self.root.update()
            except self.tk.TclError:
                self.close()
        return self.done

    def close(self):
        if not self.done:
            self.done = True
            try:
                self.root.destroy()
            except self.tk.TclError:
                pass


def edit_fields(title, fields, parse):
    return FieldDialog(title, fields, parse)


def optional_number(value, label, *, positive=False):
    if value == "":
        return None
    try:
        number = float(value)
    except ValueError:
        raise ValueError(f"{label} must be a number, or blank if unknown.") from None
    if not math.isfinite(number) or number < 0 or (positive and number == 0):
        raise ValueError(f"{label} must be finite and {'positive' if positive else 'non-negative'}.")
    return number


def edit_unit_rules(profile):
    special_rules = profile.get("special_rules") or []
    special_rules = ", ".join(special_rules) if isinstance(special_rules, list) else str(special_rules)
    fields = [("speed_in", "Speed (inches)", profile.get("speed_in"), "number"),
              ("height", "Rule Height", profile.get("height"), "number"),
              ("side", "Side / army", profile.get("side"), "text"),
              ("unit_kind", "Unit kind (blank = unknown)", profile.get("unit_kind"), ("", "ordinary", "war_engine", "individual")),
              ("special_rules", "Special rules (comma separated)", special_rules, "text"),
              ("engaged", "Currently Engaged", profile.get("engaged"), "bool"),
              ("wavering", "Currently Wavering", profile.get("wavering"), "bool")]

    def parse(values):
        values["speed_in"] = optional_number(values["speed_in"], "Speed")
        values["height"] = optional_number(values["height"], "Height")
        values["side"] = values["side"].strip() or None
        values["unit_kind"] = values["unit_kind"] or None
        values["special_rules"] = [s.strip() for s in values["special_rules"].split(",") if s.strip()]
        return values

    return edit_fields("Unit rule information", fields, parse)


def edit_terrain():
    def parse(values):
        if not values["label"].strip():
            raise ValueError("Enter a terrain label.")
        values["height"] = optional_number(values["height"], "Height")
        values["label"] = values["label"].strip()
        return values

    return edit_fields("Terrain information", [("label", "Label", "Terrain", "text"),
        ("kind", "Terrain kind", "blocking", ("blocking", "difficult", "obstacle", "hill", "decorative")),
        ("height", "Rule Height (blank = unknown)", None, "number")], parse)
