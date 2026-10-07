# -*- coding: utf-8 -*-
"""Python 3.11. Копирует CR2/CR3/RAW по именам отобранных JPG/JPEG/PNG. Без сторонних библиотек."""
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import os
import shutil

SELECTION_ROOT = None
RAW_ROOT = None
GROUPS = ("",)
OUTPUT_ROOT = None


def read_path(prompt, default=None):
    while True:
        value = input(prompt).strip().strip('"').strip("'")
        if not value:
            if default is not None:
                return default
            print("Вставьте путь к папке из адресной строки Проводника.")
            continue
        return Path(value).expanduser()


def configure():
    global SELECTION_ROOT, RAW_ROOT, OUTPUT_ROOT
    print("Скопируйте пути из адресной строки Проводника и вставьте сюда.")
    print("Поиск JPG и CR3 включает вложенные папки.")
    SELECTION_ROOT = read_path("Папка с отобранными JPG: ")
    RAW_ROOT = read_path("Папка с исходными CR3: ")
    default = SELECTION_ROOT / "Отбор_RAW"
    OUTPUT_ROOT = read_path(
        f"Папка для копий RAW [Enter = {default}]: ", default)
    raw = RAW_ROOT.resolve()
    output = OUTPUT_ROOT.resolve()
    if output == raw or raw.is_relative_to(output) or output.is_relative_to(raw):
        raise ValueError("Папка результата и папка исходных RAW должны быть отдельными и не вложенными друг в друга.")


def scan(folder, extensions):
    # os.walk с onerror не скрывает ошибки доступа к вложенным папкам.
    def fail(error):
        raise error
    for current, dirs, files in os.walk(folder, onerror=fail):
        dirs.sort()
        for name in sorted(files):
            path = Path(current) / name
            if path.suffix.casefold() in extensions:
                yield path


def main():
    required = [RAW_ROOT, *(SELECTION_ROOT / group for group in GROUPS)]
    for folder in required:
        if not folder.is_dir():
            raise FileNotFoundError(f"Папка не найдена: {folder}")

    print("Индексирую CR2 / CR3 / RAW, включая вложенные папки…")
    index = defaultdict(list)
    for raw in scan(RAW_ROOT, {".cr3", ".cr2", ".raw"}):
        index[raw.stem.casefold()].append(raw)
    # Сначала читаем все отборы; при ошибке чтения копирование не начинается.
    selections = {group: list(scan(SELECTION_ROOT / group, {".jpg", ".jpeg", ".png"}))
                  for group in GROUPS}
    lines = [f"Запуск: {datetime.now():%Y-%m-%d %H:%M:%S}",
             f"Источник: {RAW_ROOT}", f"Результат: {OUTPUT_ROOT}",
             f"Найдено RAW: {sum(map(len, index.values()))}"]
    totals = defaultdict(int)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for group, jpgs in selections.items():
        target_dir = OUTPUT_ROOT / group
        target_dir.mkdir(parents=True, exist_ok=True)
        counts = defaultdict(int)
        seen = set()
        lines.append(f"\n=== {group}: JPG/JPEG/PNG {len(jpgs)} ===")
        for jpg in jpgs:
            key = jpg.stem.casefold()
            if key in seen:
                continue
            seen.add(key)
            matches = index.get(key, [])
            if not matches:
                counts["не найдено"] += 1
                lines.append(f"НЕ НАЙДЕНО: {jpg}")
                continue
            by_format = defaultdict(list)
            for candidate in matches:
                by_format[candidate.suffix.casefold()].append(candidate)
            for extension, candidates in sorted(by_format.items()):
                if len(candidates) > 1:
                    counts["неоднозначно"] += 1
                    lines.append(f"НЕОДНОЗНАЧНО ({extension}): {jpg} — пропущено; кандидаты:")
                    lines.extend(f"  {p}" for p in candidates)
                    continue
                source = candidates[0]
                destination = target_dir / source.name
                created = False
                try:
                    # Режим xb защищает существующие файлы от перезаписи.
                    with destination.open("xb") as out:
                        created = True
                        with source.open("rb") as inp:
                            shutil.copyfileobj(inp, out, length=1024 * 1024)
                    shutil.copystat(source, destination)
                    counts["скопировано"] += 1
                    print(f"{source.name}")
                    lines.append(f"СКОПИРОВАНО: {source} -> {destination}")
                except FileExistsError:
                    counts["уже существует"] += 1
                    lines.append(f"УЖЕ СУЩЕСТВУЕТ (не проверялось): {destination}")
                except (OSError, KeyboardInterrupt):
                    if created:
                        destination.unlink(missing_ok=True)
                    raise
        summary = "; ".join(f"{name}: {counts[name]}" for name in
                            ("скопировано", "уже существует", "не найдено", "неоднозначно"))
        print(f"\n{group or 'Отбор'}: {summary}\n")
        lines.append(summary)
        for name, value in counts.items():
            totals[name] += value
    report = OUTPUT_ROOT / f"Отчёт_{datetime.now():%Y-%m-%d_%H-%M-%S_%f}.txt"
    report.write_text("\n".join(lines), encoding="utf-8-sig")
    print(f"Готово. Скопировано: {totals['скопировано']}.")
    print(f"Папки с RAW: {OUTPUT_ROOT}")
    print(f"Отчёт: {report}")



# Оконный интерфейс на встроенном Tkinter.
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
from contextlib import redirect_stdout


class QueueWriter:
    def __init__(self, events):
        self.events = events

    def write(self, text):
        if text:
            self.events.put(("log", text))
        return len(text)

    def flush(self):
        pass


class Application:
    def __init__(self, root):
        self.root = root
        self.running = False
        self.events = queue.Queue()
        self.last_output = None
        root.title("Отбор фотографий — JPG / PNG → RAW")
        root.geometry("850x600")
        root.minsize(680, 470)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("TButton", padding=6)
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(9, weight=1)
        ttk.Label(frame, text="Отбор RAW по именам файлов", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Вставьте пути из Проводника или выберите папки кнопками справа.").grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 18))
        self.values = [tk.StringVar() for _ in range(3)]
        self.controls = []
        for i, label in enumerate(("Отобранные JPG / JPEG / PNG", "Исходные CR2 / CR3 / RAW", "Папка для копий RAW")):
            ttk.Label(frame, text=label).grid(row=2+i*2, column=0, sticky="w")
            entry = ttk.Entry(frame, textvariable=self.values[i])
            entry.grid(row=3+i*2, column=0, sticky="ew", pady=(4, 10), padx=(0, 8))
            button = ttk.Button(frame, text="Выбрать…", command=lambda n=i: self.browse(n))
            button.grid(row=3+i*2, column=1, sticky="ew", pady=(4, 10))
            self.controls.extend((entry, button))
        bar = ttk.Frame(frame)
        bar.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        self.start_button = ttk.Button(bar, text="Скопировать RAW", command=self.start)
        self.start_button.pack(side="left")
        self.open_button = ttk.Button(bar, text="Открыть результат", command=self.open_output, state="disabled")
        self.open_button.pack(side="left", padx=10)
        self.status = tk.StringVar(value="Готов к работе")
        ttk.Label(bar, textvariable=self.status).pack(side="right")
        log_frame = ttk.Frame(frame)
        log_frame.grid(row=9, column=0, columnspan=2, sticky="nsew")
        self.log = tk.Text(log_frame, wrap="word", font=("Consolas", 10), state="disabled", height=10)
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)
        ttk.Label(frame, text="Поиск включает вложенные папки. Существующие копии не перезаписываются.").grid(row=10, column=0, columnspan=2, sticky="w", pady=(10, 0))
        root.after(100, self.poll)

    def browse(self, index):
        path = filedialog.askdirectory(title="Выберите папку", mustexist=index != 2)
        if path:
            self.values[index].set(path)

    def append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self):
        global SELECTION_ROOT, RAW_ROOT, OUTPUT_ROOT
        if self.running:
            return
        paths = [v.get().strip().strip('"').strip("'") for v in self.values]
        if not paths[0] or not paths[1]:
            messagebox.showerror("Не указаны папки", "Укажите папку с JPG/PNG и папку с исходными CR2/CR3/RAW.")
            return
        SELECTION_ROOT = Path(paths[0]).expanduser()
        RAW_ROOT = Path(paths[1]).expanduser()
        OUTPUT_ROOT = Path(paths[2]).expanduser() if paths[2] else SELECTION_ROOT / "Отбор_RAW"
        try:
            if not SELECTION_ROOT.is_dir() or not RAW_ROOT.is_dir():
                raise ValueError("Папка с JPG/PNG или RAW не найдена. Проверьте пути.")
            raw, output = RAW_ROOT.resolve(), OUTPUT_ROOT.resolve()
            if output == raw or output.is_relative_to(raw) or raw.is_relative_to(output):
                raise ValueError("Папка результата должна быть отдельной от исходных RAW и не вложенной в неё.")
        except (OSError, ValueError) as error:
            messagebox.showerror("Проверьте пути", str(error))
            return
        self.values[2].set(str(OUTPUT_ROOT))
        self.last_output = OUTPUT_ROOT
        self.running = True
        self.status.set("Копирование…")
        for control in self.controls + [self.start_button, self.open_button]:
            control.configure(state="disabled")
        self.append("\n── Новый запуск ──\n")
        threading.Thread(target=self.worker, daemon=False).start()

    def worker(self):
        try:
            with redirect_stdout(QueueWriter(self.events)):
                main()
            self.events.put(("done", None))
        except Exception as error:
            self.events.put(("error", str(error)))

    def poll(self):
        # Ограничиваем обработку очереди, чтобы большой журнал не блокировал окно.
        for _ in range(200):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.append(value)
            else:
                self.running = False
                for control in self.controls + [self.start_button]:
                    control.configure(state="normal")
                self.open_button.configure(state="normal" if self.last_output and self.last_output.is_dir() else "disabled")
                if kind == "done":
                    self.status.set("Готово — проверьте отчёт")
                else:
                    self.status.set("Ошибка")
                    self.append(f"\nОШИБКА: {value}\nГотовые копии сохранены.\n")
                    messagebox.showerror("Ошибка копирования", value)
        self.root.after(100, self.poll)

    def open_output(self):
        if self.last_output:
            try:
                os.startfile(str(self.last_output))
            except OSError as error:
                messagebox.showerror("Не удалось открыть папку", str(error))

    def close(self):
        if self.running:
            messagebox.showinfo("Идёт копирование", "Дождитесь окончания копирования перед закрытием окна.")
        else:
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Application(root)
    root.mainloop()
