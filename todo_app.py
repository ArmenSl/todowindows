"""Local Windows desktop todo application using Tkinter and SQLite."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

DB_PATH = Path(__file__).with_name("todo_app.db")
PRIORITIES = ("LOW", "MEDIUM", "HIGH", "URGENT")
STATUSES = ("TODO", "IN_PROGRESS", "DONE", "CANCELLED")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class TodoDatabase:
    """SQLite persistence for all entities and associations in the domain model."""
    def __init__(self) -> None:
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.create_schema()
        self.seed_user()

    def create_schema(self) -> None:
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, username TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS todo_lists (
          id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          name TEXT NOT NULL CHECK(trim(name) <> ''), description TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS todo_items (
          id INTEGER PRIMARY KEY, list_id INTEGER NOT NULL REFERENCES todo_lists(id) ON DELETE CASCADE,
          title TEXT NOT NULL CHECK(trim(title) <> ''), description TEXT, due_date TEXT,
          completed_at TEXT, is_archived INTEGER NOT NULL DEFAULT 0 CHECK(is_archived IN (0,1)),
          priority TEXT NOT NULL CHECK(priority IN ('LOW','MEDIUM','HIGH','URGENT')),
          status TEXT NOT NULL CHECK(status IN ('TODO','IN_PROGRESS','DONE','CANCELLED')),
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tags (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE CHECK(trim(name) <> ''),
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS item_tags (
          item_id INTEGER NOT NULL REFERENCES todo_items(id) ON DELETE CASCADE,
          tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
          PRIMARY KEY(item_id, tag_id)
        );
        CREATE TABLE IF NOT EXISTS comments (
          id INTEGER PRIMARY KEY, todo_item_id INTEGER NOT NULL REFERENCES todo_items(id) ON DELETE CASCADE,
          author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          body TEXT NOT NULL CHECK(trim(body) <> ''), created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reminders (
          id INTEGER PRIMARY KEY, todo_item_id INTEGER NOT NULL REFERENCES todo_items(id) ON DELETE CASCADE,
          remind_at TEXT NOT NULL, is_sent INTEGER NOT NULL DEFAULT 0 CHECK(is_sent IN (0,1)),
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attachments (
          id INTEGER PRIMARY KEY, todo_item_id INTEGER NOT NULL REFERENCES todo_items(id) ON DELETE CASCADE,
          file_name TEXT NOT NULL, file_size_bytes INTEGER NOT NULL CHECK(file_size_bytes >= 0), mime_type TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """)
        self.conn.commit()

    def seed_user(self) -> None:
        if not self.conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            stamp = now()
            self.conn.execute("INSERT INTO users(email,username,display_name,created_at,updated_at) VALUES(?,?,?,?,?)",
                              ("local@todo.app", "local", "Local User", stamp, stamp))
            self.conn.commit()

    def query(self, sql: str, values: tuple = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, values).fetchall()

    def one(self, sql: str, values: tuple = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, values).fetchone()

    def execute(self, sql: str, values: tuple = ()) -> int:
        cur = self.conn.execute(sql, values)
        self.conn.commit()
        return int(cur.lastrowid)

    def default_list_id(self) -> int:
        row = self.one("SELECT id FROM todo_lists LIMIT 1")
        if row:
            return int(row["id"])
        stamp = now()
        user_id = self.one("SELECT id FROM users LIMIT 1")["id"]
        return self.execute("INSERT INTO todo_lists(owner_id,name,description,created_at,updated_at) VALUES(?,?,?,?,?)",
                            (user_id, "Inbox", "Your default todo list", stamp, stamp))


class TodoApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.db = TodoDatabase()
        self.title("Win11 Todo")
        self.geometry("1180x720")
        self.minsize(940, 580)
        self.configure(bg="#f6f7fb")
        self.selected_item_id: int | None = None
        self._style()
        self._build()
        self.refresh_all()

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("App.TFrame", background="#f6f7fb")
        style.configure("Sidebar.TFrame", background="#18243a")
        style.configure("Header.TLabel", background="#f6f7fb", foreground="#18243a", font=("Segoe UI", 20, "bold"))
        style.configure("Info.TLabel", background="#f6f7fb", foreground="#526079", font=("Segoe UI", 10))
        style.configure("Side.TButton", background="#243759", foreground="white", borderwidth=0, font=("Segoe UI", 10), padding=10)
        style.map("Side.TButton", background=[("active", "#6366f1")])
        style.configure("Accent.TButton", background="#6366f1", foreground="white", borderwidth=0, font=("Segoe UI", 10, "bold"), padding=(14, 9))
        style.map("Accent.TButton", background=[("active", "#4f46e5")])
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=30, background="white", fieldbackground="white", foreground="#18243a")
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#e8ecf5", foreground="#18243a")

    def _build(self) -> None:
        sidebar = ttk.Frame(self, style="Sidebar.TFrame", width=190)
        sidebar.pack(side="left", fill="y")
        ttk.Label(sidebar, text="  WIN11 TODO", background="#18243a", foreground="white", font=("Segoe UI", 15, "bold")).pack(pady=(24, 18), anchor="w")
        for label, action in [("Tasks", self.show_tasks), ("Lists", self.manage_lists), ("Tags", self.manage_tags), ("People", self.manage_users), ("Reminders", self.manage_reminders)]:
            ttk.Button(sidebar, text=label, style="Side.TButton", command=action).pack(fill="x", padx=12, pady=3)
        ttk.Label(sidebar, text="Local SQLite storage", background="#18243a", foreground="#b8c4db", font=("Segoe UI", 9)).pack(side="bottom", pady=18)

        root = ttk.Frame(self, style="App.TFrame", padding=24)
        root.pack(side="left", fill="both", expand=True)
        top = ttk.Frame(root, style="App.TFrame")
        top.pack(fill="x")
        self.heading = ttk.Label(top, text="My tasks", style="Header.TLabel")
        self.heading.pack(side="left")
        ttk.Button(top, text="+ New task", style="Accent.TButton", command=self.new_task).pack(side="right")
        self.info = ttk.Label(root, text="", style="Info.TLabel")
        self.info.pack(anchor="w", pady=(4, 16))

        split = ttk.Panedwindow(root, orient="horizontal")
        split.pack(fill="both", expand=True)
        left = ttk.Frame(split, style="App.TFrame", padding=(0, 0, 14, 0))
        right = ttk.Frame(split, style="App.TFrame", padding=(14, 0, 0, 0))
        split.add(left, weight=3); split.add(right, weight=2)
        cols = ("status", "priority", "title", "due", "list")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        for key, text, width in [("status", "Status", 115), ("priority", "Priority", 95), ("title", "Title", 270), ("due", "Due", 105), ("list", "List", 125)]:
            self.tree.heading(key, text=text); self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.show_selected())
        buttons = ttk.Frame(left, style="App.TFrame")
        buttons.pack(fill="x", pady=12)
        for text, command in [("Complete / reopen", self.toggle_complete), ("Postpone", self.postpone), ("Edit", self.edit_task), ("Archive", self.archive_task), ("Delete", self.delete_task)]:
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=(0, 7))

        ttk.Label(right, text="Task details", style="Header.TLabel", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        self.detail = tk.Text(right, height=17, wrap="word", font=("Segoe UI", 10), background="white", foreground="#18243a", relief="flat", padx=14, pady=14)
        self.detail.pack(fill="both", expand=True, pady=(12, 10))
        self.detail.configure(state="disabled")
        actions = ttk.Frame(right, style="App.TFrame")
        actions.pack(fill="x")
        for text, command in [("Add comment", self.add_comment), ("Add reminder", self.add_reminder), ("Add attachment", self.add_attachment), ("Manage tags", self.assign_tags)]:
            ttk.Button(actions, text=text, command=command).pack(side="left", padx=(0, 6), pady=3)

    def refresh_all(self) -> None:
        self.tree.delete(*self.tree.get_children())
        rows = self.db.query("""SELECT i.*, l.name list_name FROM todo_items i JOIN todo_lists l ON l.id=i.list_id
                              WHERE i.is_archived=0 ORDER BY CASE i.status WHEN 'DONE' THEN 1 ELSE 0 END, i.due_date IS NULL, i.due_date, i.id DESC""")
        for row in rows:
            self.tree.insert("", "end", iid=str(row["id"]), values=(row["status"], row["priority"], row["title"], row["due_date"] or "—", row["list_name"]))
        self.info.config(text=f"{len(rows)} active task{'s' if len(rows) != 1 else ''} • all data stays on this computer")
        self.show_selected()

    def selected(self) -> int | None:
        picks = self.tree.selection()
        if not picks:
            messagebox.showinfo("Select a task", "Choose a task first.")
            return None
        return int(picks[0])

    def show_selected(self) -> None:
        picks = self.tree.selection()
        self.detail.configure(state="normal"); self.detail.delete("1.0", "end")
        if not picks:
            self.detail.insert("end", "Select a task to view its description, tags, comments, reminders, and attachments.")
        else:
            item_id = int(picks[0]); item = self.db.one("SELECT * FROM todo_items WHERE id=?", (item_id,))
            tags = ", ".join(r["name"] for r in self.db.query("SELECT t.name FROM tags t JOIN item_tags it ON it.tag_id=t.id WHERE it.item_id=?", (item_id,))) or "None"
            comments = self.db.query("SELECT c.body,u.display_name FROM comments c JOIN users u ON u.id=c.author_id WHERE c.todo_item_id=? ORDER BY c.id", (item_id,))
            reminders = self.db.query("SELECT remind_at,is_sent FROM reminders WHERE todo_item_id=? ORDER BY remind_at", (item_id,))
            attachments = self.db.query("SELECT file_name,file_size_bytes,mime_type FROM attachments WHERE todo_item_id=?", (item_id,))
            lines = [item["title"], "", f"Status: {item['status']}     Priority: {item['priority']}", f"Due date: {item['due_date'] or 'Not set'}", f"Completed at: {item['completed_at'] or '—'}", f"Tags: {tags}", "", "Description", item["description"] or "—", "", "Comments"]
            lines += [f"• {r['display_name']}: {r['body']}" for r in comments] or ["—"]
            lines += ["", "Reminders"] + [f"• {r['remind_at']} {'(sent)' if r['is_sent'] else '(pending)'}" for r in reminders] or ["—"]
            lines += ["", "Attachments"] + [f"• {r['file_name']} ({r['file_size_bytes']} bytes, {r['mime_type']})" for r in attachments] or ["—"]
            self.detail.insert("end", "\n".join(lines))
        self.detail.configure(state="disabled")

    def task_dialog(self, item: sqlite3.Row | None = None) -> dict | None:
        win = tk.Toplevel(self); win.title("Edit task" if item else "New task"); win.transient(self); win.grab_set(); win.configure(bg="#f6f7fb")
        values = {"title":"", "description":"", "due_date":"", "priority":"MEDIUM", "status":"TODO", "list_id":self.db.default_list_id()}
        if item: values.update(dict(item))
        fields: dict[str, tk.Widget] = {}
        form = ttk.Frame(win, padding=22, style="App.TFrame"); form.pack(fill="both", expand=True)
        ttk.Label(form, text="Task", style="Header.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        def label(text: str, row: int) -> None: ttk.Label(form, text=text, style="Info.TLabel").grid(row=row, column=0, sticky="nw", padx=(0,12), pady=7)
        label("Title", 1); title = ttk.Entry(form, width=48); title.insert(0, values["title"]); title.grid(row=1,column=1,sticky="ew", pady=7); fields["title"] = title
        label("Description", 2); desc = tk.Text(form, width=42, height=5, font=("Segoe UI",10)); desc.insert("1.0", values["description"] or ""); desc.grid(row=2,column=1,sticky="ew", pady=7); fields["description"] = desc
        label("Due date (YYYY-MM-DD)", 3); due=ttk.Entry(form); due.insert(0, values["due_date"] or ""); due.grid(row=3,column=1,sticky="ew",pady=7); fields["due_date"] = due
        label("Priority", 4); priority=ttk.Combobox(form,values=PRIORITIES,state="readonly"); priority.set(values["priority"]); priority.grid(row=4,column=1,sticky="ew",pady=7); fields["priority"] = priority
        label("Status", 5); status=ttk.Combobox(form,values=STATUSES,state="readonly"); status.set(values["status"]); status.grid(row=5,column=1,sticky="ew",pady=7); fields["status"] = status
        lists=self.db.query("SELECT id,name FROM todo_lists ORDER BY name"); lookup={r['name']:r['id'] for r in lists}; reverse={r['id']:r['name'] for r in lists}
        label("List", 6); list_box=ttk.Combobox(form,values=list(lookup),state="readonly"); list_box.set(reverse.get(values["list_id"],"")); list_box.grid(row=6,column=1,sticky="ew",pady=7)
        result: dict | None = None
        def save() -> None:
            nonlocal result
            try:
                due_value = due.get().strip()
                if due_value: date.fromisoformat(due_value)
                if not title.get().strip(): raise ValueError("Title is required.")
                result={"title":title.get().strip(),"description":desc.get("1.0","end-1c").strip() or None,"due_date":due_value or None,"priority":priority.get(),"status":status.get(),"list_id":lookup[list_box.get()]}
                win.destroy()
            except (ValueError, KeyError): messagebox.showerror("Invalid task", "Enter a title and a valid YYYY-MM-DD due date.", parent=win)
        ttk.Button(form,text="Save task",style="Accent.TButton",command=save).grid(row=7,column=1,sticky="e",pady=(16,0)); form.columnconfigure(1,weight=1)
        self.wait_window(win); return result

    def new_task(self) -> None:
        data = self.task_dialog()
        if data:
            stamp=now(); completed=stamp if data["status"]=="DONE" else None
            self.db.execute("INSERT INTO todo_items(list_id,title,description,due_date,completed_at,is_archived,priority,status,created_at,updated_at) VALUES(?,?,?,?,?,0,?,?,?,?)", (data["list_id"],data["title"],data["description"],data["due_date"],completed,data["priority"],data["status"],stamp,stamp)); self.refresh_all()

    def edit_task(self) -> None:
        item_id=self.selected()
        if item_id is None:return
        old=self.db.one("SELECT * FROM todo_items WHERE id=?",(item_id,)); data=self.task_dialog(old)
        if data:
            stamp=now(); completed=stamp if data["status"]=="DONE" and old["status"]!="DONE" else (None if data["status"]!="DONE" else old["completed_at"])
            self.db.execute("UPDATE todo_items SET list_id=?,title=?,description=?,due_date=?,priority=?,status=?,completed_at=?,updated_at=? WHERE id=?",(data["list_id"],data["title"],data["description"],data["due_date"],data["priority"],data["status"],completed,stamp,item_id));self.refresh_all()

    def toggle_complete(self) -> None:
        item_id=self.selected()
        if item_id is None:return
        item=self.db.one("SELECT status FROM todo_items WHERE id=?",(item_id,)); done=item["status"]!="DONE"; self.db.execute("UPDATE todo_items SET status=?,completed_at=?,updated_at=? WHERE id=?",("DONE" if done else "TODO",now() if done else None,now(),item_id));self.refresh_all()

    def postpone(self) -> None:
        item_id=self.selected()
        if item_id is None:return
        days=simpledialog.askinteger("Postpone task","How many days?",parent=self,minvalue=1)
        if days is None:return
        row=self.db.one("SELECT due_date FROM todo_items WHERE id=?",(item_id,)); base=date.fromisoformat(row["due_date"]) if row["due_date"] else date.today(); self.db.execute("UPDATE todo_items SET due_date=?,updated_at=? WHERE id=?",((base+timedelta(days=days)).isoformat(),now(),item_id));self.refresh_all()

    def archive_task(self) -> None:
        item_id=self.selected()
        if item_id is not None:self.db.execute("UPDATE todo_items SET is_archived=1,updated_at=? WHERE id=?",(now(),item_id));self.refresh_all()

    def delete_task(self) -> None:
        item_id=self.selected()
        if item_id is not None and messagebox.askyesno("Delete task","Delete this task and all its comments, reminders, attachments, and tag links?"):
            self.db.execute("DELETE FROM todo_items WHERE id=?",(item_id,));self.refresh_all()

    def add_comment(self) -> None:
        item_id=self.selected()
        if item_id is None:return
        body=simpledialog.askstring("Add comment","Comment text:",parent=self)
        if body and body.strip():
            stamp=now(); author=self.db.one("SELECT id FROM users LIMIT 1")["id"];self.db.execute("INSERT INTO comments(todo_item_id,author_id,body,created_at,updated_at) VALUES(?,?,?,?,?)",(item_id,author,body.strip(),stamp,stamp));self.show_selected()

    def add_reminder(self) -> None:
        item_id=self.selected()
        if item_id is None:return
        value=simpledialog.askstring("Add reminder","Date and time (YYYY-MM-DDTHH:MM):",parent=self)
        try:
            datetime.fromisoformat(value or "")
            stamp=now();self.db.execute("INSERT INTO reminders(todo_item_id,remind_at,is_sent,created_at,updated_at) VALUES(?,?,0,?,?)",(item_id,value,stamp,stamp));self.show_selected()
        except ValueError: messagebox.showerror("Invalid reminder","Use ISO date/time, such as 2026-01-31T09:30.")

    def add_attachment(self) -> None:
        item_id=self.selected()
        if item_id is None:return
        path=filedialog.askopenfilename(parent=self)
        if path:
            file=Path(path); stamp=now(); mime="application/octet-stream";self.db.execute("INSERT INTO attachments(todo_item_id,file_name,file_size_bytes,mime_type,created_at,updated_at) VALUES(?,?,?,?,?,?)",(item_id,file.name,file.stat().st_size,mime,stamp,stamp));self.show_selected()

    def assign_tags(self) -> None:
        item_id=self.selected()
        if item_id is None:return
        tags=self.db.query("SELECT id,name FROM tags ORDER BY name")
        if not tags: messagebox.showinfo("No tags","Create a tag in the Tags screen first.");return
        choices="\n".join(f"{r['id']}: {r['name']}" for r in tags); value=simpledialog.askinteger("Manage tags",f"Enter a tag ID to toggle:\n{choices}",parent=self)
        if value is not None:
            try:
                if self.db.one("SELECT 1 FROM item_tags WHERE item_id=? AND tag_id=?",(item_id,value)): self.db.execute("DELETE FROM item_tags WHERE item_id=? AND tag_id=?",(item_id,value))
                else:self.db.execute("INSERT INTO item_tags(item_id,tag_id) VALUES(?,?)",(item_id,value))
                self.show_selected()
            except sqlite3.IntegrityError: messagebox.showerror("Invalid tag","That tag does not exist.")

    def manage_lists(self) -> None: self.manage_simple("todo_lists", "Lists", ["name", "description"], "owner_id")
    def manage_tags(self) -> None: self.manage_simple("tags", "Tags", ["name"])
    def manage_users(self) -> None: self.manage_simple("users", "People", ["email", "username", "display_name"])
    def manage_reminders(self) -> None:
        rows=self.db.query("SELECT r.id,r.remind_at,r.is_sent,i.title FROM reminders r JOIN todo_items i ON i.id=r.todo_item_id ORDER BY r.remind_at")
        messagebox.showinfo("Reminders", "\n".join(f"#{r['id']} • {r['title']} • {r['remind_at']} • {'sent' if r['is_sent'] else 'pending'}" for r in rows) or "No reminders.")

    def manage_simple(self, table: str, title: str, fields: list[str], extra: str | None = None) -> None:
        rows=self.db.query(f"SELECT * FROM {table} ORDER BY id")
        rendered="\n".join(f"#{r['id']}  " + " | ".join(str(r[f] or "") for f in fields) for r in rows) or "No entries yet."
        answer=messagebox.askyesno(title,rendered+"\n\nAdd a new entry?")
        if not answer:return
        data=[]
        for field in fields:
            val=simpledialog.askstring(title,f"{field.replace('_',' ').title()}:",parent=self)
            if val is None:return
            data.append(val.strip())
        if not all(data):messagebox.showerror(title,"All fields are required.");return
        stamp=now()
        try:
            if table=="todo_lists": self.db.execute("INSERT INTO todo_lists(owner_id,name,description,created_at,updated_at) VALUES(?,?,?,?,?)",(self.db.one("SELECT id FROM users LIMIT 1")["id"],data[0],data[1] or None,stamp,stamp))
            elif table=="tags": self.db.execute("INSERT INTO tags(name,created_at,updated_at) VALUES(?,?,?)",(data[0],stamp,stamp))
            else:self.db.execute("INSERT INTO users(email,username,display_name,created_at,updated_at) VALUES(?,?,?,?,?)",(*data,stamp,stamp))
            self.refresh_all()
        except sqlite3.IntegrityError:messagebox.showerror(title,"That unique value is already in use.")

    def show_tasks(self) -> None:
        self.heading.config(text="My tasks");self.refresh_all()


def main() -> None:
    TodoApp().mainloop()


if __name__ == "__main__":
    main()
