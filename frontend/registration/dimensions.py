"""Draft tray dimensions for the two imported type catalogs."""

import math


def parse_dimensions(rows):
    dimensions = {}
    for type_id, (width, depth) in rows.items():
        width, depth = width.strip(), depth.strip()
        if not width and not depth:
            dimensions[type_id] = None
            continue
        if not width or not depth:
            raise ValueError(f"{type_id}: enter both width and depth, or leave both blank.")
        try:
            values = [float(width), float(depth)]
        except ValueError:
            raise ValueError(f"{type_id}: dimensions must be positive numbers in mm.") from None
        if any(not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError(f"{type_id}: dimensions must be finite and greater than zero.")
        dimensions[type_id] = dict(zip(("width_mm", "depth_mm"), values))
    return dimensions


def edit_type_dimensions(roster):
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("Tray dimensions")
    root.attributes("-topmost", True)
    root.geometry("1040x680")
    root.minsize(720, 360)
    root.columnconfigure((0, 1), weight=1, uniform="lists")
    root.rowconfigure(1, weight=1)
    ttk.Label(root, text="Width = front edge; depth = front to back. All dimensions are in mm.\n"
              "Leave both fields blank if unknown. Save applies to every instance of the type.").grid(
                  row=0, column=0, columnspan=2, padx=14, pady=12, sticky="w")
    variables, result, scroll_areas = {}, [], {}
    for column, list_id in enumerate(("A", "B")):
        types = [(key, row) for key, row in roster.types.items() if row.get("list_id", "A") == list_id]
        group = ttk.LabelFrame(root, text=f"List {list_id} / {len(types)} types")
        group.grid(row=1, column=column, padx=10, pady=4, sticky="nsew")
        group.columnconfigure(0, weight=1)
        group.rowconfigure(0, weight=1)
        canvas = tk.Canvas(group, highlightthickness=0, width=460)
        scrollbar = ttk.Scrollbar(group, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        body = ttk.Frame(canvas, padding=8)
        item = canvas.create_window((0, 0), window=body, anchor="nw")
        body.columnconfigure(0, weight=1)
        body.bind("<Configure>", lambda event, view=canvas: view.configure(scrollregion=view.bbox("all")))
        canvas.bind("<Configure>", lambda event, view=canvas, window=item: view.itemconfigure(window, width=event.width))
        scroll_areas[group] = canvas
        for index, label in enumerate(("Type", "Width (mm)", "Depth (mm)")):
            ttk.Label(body, text=label).grid(row=0, column=index, padx=4, pady=6, sticky="w")
        if not types:
            ttk.Label(body, text=f"Import list {list_id} to add types.").grid(
                row=1, column=0, columnspan=3, padx=4, pady=14, sticky="w")
        for index, (type_id, record) in enumerate(types, start=1):
            description = record.get("unit_name", record.get("name", type_id))
            if record.get("formation"):
                description += " / " + record["formation"]
            text = f"Type {record.get('type_number', index)} ({type_id})\n{description}"
            label = ttk.Label(body, text=text, wraplength=235)
            label.grid(row=index, column=0, padx=4, pady=9, sticky="ew")
            label.bind("<Configure>", lambda event: event.widget.configure(wraplength=max(80, event.width)))
            dimension = record.get("dimension") or {}
            fields = []
            for field_column, field in enumerate(("width_mm", "depth_mm"), start=1):
                value = dimension.get(field)
                variable = tk.StringVar(master=root, value="" if value is None else str(value))
                ttk.Entry(body, textvariable=variable, width=10).grid(row=index, column=field_column, padx=4, pady=9)
                fields.append(variable)
            variables[type_id] = fields

    def scroll(event):
        widget = event.widget
        while widget is not None and widget not in scroll_areas:
            widget = widget.master
        if widget is not None and event.delta:
            steps = -int(event.delta / 120) or (-1 if event.delta > 0 else 1)
            scroll_areas[widget].yview_scroll(steps, "units")
            return "break"

    def save():
        try:
            dimensions = parse_dimensions({key: (width.get(), depth.get()) for key, (width, depth) in variables.items()})
        except ValueError as error:
            messagebox.showerror("Tray dimensions", str(error), parent=root)
            return
        result.append(dimensions)
        root.destroy()

    footer = ttk.Frame(root)
    footer.grid(row=2, column=0, columnspan=2, padx=14, pady=12, sticky="e")
    ttk.Button(footer, text="Save", command=save).grid(row=0, column=0, padx=6)
    ttk.Button(footer, text="Cancel", command=root.destroy).grid(row=0, column=1, padx=6)
    root.bind("<MouseWheel>", scroll)
    root.bind("<Escape>", lambda event: root.destroy())
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    try:
        root.mainloop()
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
    return result[0] if result else None
