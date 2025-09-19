import os
import sys
import random
import json
import pygame
import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
from PIL import Image, ImageTk

# Initialize CustomTkinter appearance once
ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and PyInstaller """
    try:
        base_path = sys._MEIPASS  # PyInstaller temp folder when bundled
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class SplashScreen(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)

        splash_path = resource_path("logo.png")
        try:
            img = Image.open(splash_path)
            self.splash_image = ImageTk.PhotoImage(img)
            width, height = img.size
        except Exception as e:
            print(f"Warning: Unable to load splash image: {e}")
            width, height = 400, 200
            self.splash_image = None

        self.overrideredirect(True)
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.lift()

        if self.splash_image:
            label = tk.Label(self, image=self.splash_image, borderwidth=0)
            label.pack()

        self.progress = ctk.CTkProgressBar(self, width=width - 40)
        self.progress.pack(pady=10, padx=20)
        self.progress.set(0)

        self.step = 0
        self.max_steps = 10
        self.progress.after(1000, self.progress_update)

    def progress_update(self):
        self.step += 1
        self.progress.set(self.step / self.max_steps)
        if self.step < self.max_steps:
            self.progress.after(1000, self.progress_update)
        else:
            self.destroy()


class ExamApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CBT App")

        # Set app icon from logo.png
        icon_path = resource_path("logo.png")
        try:
            img = Image.open(icon_path)
            icon_img = ImageTk.PhotoImage(img)
            self.root.iconphoto(False, icon_img)
        except Exception as e:
            print(f"Warning: Could not set app icon: {e}")

        self.sessions = self.load_all_sessions()
        for new_session in ["Biology", "Data Processing", "Civic"]:
            if new_session not in self.sessions:
                self.sessions[new_session] = []

        sessions_keys = list(self.sessions.keys())
        sessions_keys.insert(0, "Live - All Subjects")

        self.current_session = None
        self.questions = []
        self.index = 0
        self.score = 0
        self.time_left = 60
        self.selected = ctk.StringVar(value='')
        self.user_answers = {}

        # Initialize pygame mixer before loading sound
        pygame.mixer.init()
        self.click_sound = None
        click_wav_path = resource_path("click.wav")
        try:
            self.click_sound = pygame.mixer.Sound(click_wav_path)
        except pygame.error as e:
            print(f"Warning: Unable to load sound: {e}")

        self.timer_running = False
        self.timer_id = None
        self.is_muted = False
        self.timer_paused = False

        self.build_ui(sessions_keys)
        if sessions_keys:
            self.session_select.set(sessions_keys[0])
            self.load_session(sessions_keys[0])
            self.show_question()

    def build_ui(self, sessions_keys):
        top_frame = ctk.CTkFrame(self.root)
        top_frame.pack(fill='x', pady=8, padx=8)

        ctk.CTkLabel(top_frame, text="Select Session:").pack(side='left', padx=(0, 10))
        self.session_select = ctk.CTkComboBox(top_frame, values=sessions_keys, command=self.on_session_change)
        self.session_select.pack(side='left')

        ctk.CTkLabel(top_frame, text="   Jump to Question:").pack(side='left', padx=(10, 5))

        self.question_picker = tk.Spinbox(top_frame, from_=1, to=1, width=5, command=self.jump_to_question)
        self.question_picker.pack(side='left')
        self.question_picker.bind('<Up>', lambda e: self.spinbox_step(-1))
        self.question_picker.bind('<Down>', lambda e: self.spinbox_step(1))

        question_frame = ctk.CTkFrame(self.root)
        question_frame.pack(fill='x', pady=5, padx=12)

        self.counter_label = ctk.CTkLabel(
            question_frame, text="", font=ctk.CTkFont(size=14, weight="bold"),
            text_color=ctk.ThemeManager.theme["CTkLabel"]["text_color"]
        )
        self.counter_label.pack(side='left')

        self.question_label = ctk.CTkLabel(
            self.root, text="", wraplength=400, font=ctk.CTkFont(size=16, weight="bold"),
            text_color=ctk.ThemeManager.theme["CTkLabel"]["text_color"]
        )
        self.question_label.pack(pady=(2, 15), padx=12)

        self.options_container = ctk.CTkFrame(self.root)
        self.options_container.pack(pady=10, ipadx=10, ipady=10, padx=14)

        self.progress = ctk.CTkProgressBar(self.root, width=400)
        self.progress.pack(pady=(0, 10))

        self.timer_label = ctk.CTkLabel(
            self.root, text="Time left: 60s", font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#DF1B1B"
        )
        self.timer_label.pack(pady=(0, 15))

        buttons_frame = ctk.CTkFrame(self.root)
        buttons_frame.pack(pady=6)

        self.next_button = ctk.CTkButton(buttons_frame, text="Next", command=self.next_question, state='disabled')
        self.next_button.pack(side='left', padx=10)

        self.finish_button = ctk.CTkButton(buttons_frame, text="Finish", command=self.finish_exam)
        self.finish_button.pack(side='left', padx=10)

        self.mute_button = ctk.CTkButton(buttons_frame, text="Mute", command=self.toggle_mute)
        self.mute_button.pack(side='left', padx=10)

        self.pause_button = ctk.CTkButton(buttons_frame, text="Pause Timer", command=self.toggle_timer_pause)
        self.pause_button.pack(side='left', padx=10)

        self.show_answer_button = ctk.CTkButton(buttons_frame, text="Show Answer", command=self.show_answer)
        self.show_answer_button.pack(side='left', padx=10)

    def spinbox_step(self, change):
        try:
            val = int(self.question_picker.get())
            new_val = val + change
            if 1 <= new_val <= max(1, len(self.questions)):
                self.question_picker.delete(0, 'end')
                self.question_picker.insert(0, str(new_val))
                self.jump_to_question()
        except Exception:
            pass

    def on_session_change(self, choice):
        self.load_session(choice)
        self.index = 0
        self.user_answers.clear()
        self.selected.set("")
        self.question_picker.config(from_=1, to=max(1, len(self.questions)))
        self.question_picker.delete(0, 'end')
        self.question_picker.insert(0, "1")
        self.cancel_timer()
        self.show_question()

    def load_session(self, session_name):
        self.current_session = session_name
        if session_name == "Live - All Subjects":
            combined = []
            for qlist in self.sessions.values():
                combined.extend(qlist)
            self.questions = combined
            random.shuffle(self.questions)
        else:
            self.questions = self.sessions.get(session_name, [])

        if not self.questions:
            messagebox.showwarning(title="No Questions", message=f"No questions available for session '{session_name}'.")
            self.question_label.configure(text="")
            self.counter_label.configure(text="")
            for w in self.options_container.winfo_children():
                w.destroy()
            self.questions = []
            return

    def show_question(self):
        if not self.questions:
            return
        q = self.questions[self.index]
        self.question_label.configure(text=q["question"])
        self.counter_label.configure(text=f"Question {self.index + 1} of {len(self.questions)}")

        self.selected.set(self.user_answers.get(self.index, ''))

        for widget in self.options_container.winfo_children():
            widget.destroy()

        for option in q["options"]:
            rbtn = ctk.CTkRadioButton(
                self.options_container,
                text=option,
                variable=self.selected,
                value=option,
                command=self.enable_next,
                text_color=ctk.ThemeManager.theme["CTkLabel"]["text_color"]
            )
            rbtn.pack(anchor='w')

        self.next_button.configure(state='normal' if self.selected.get() else 'disabled')

        self.reset_timer()
        self.start_timer()

    def enable_next(self):
        self.next_button.configure(state='normal')
        if not self.is_muted and self.click_sound is not None:
            self.click_sound.play()

    def reset_timer(self):
        self.time_left = 60
        self.progress.set(1)
        self.update_timer_label()

    def start_timer(self):
        if not self.timer_running:
            self.timer_running = True
            self.countdown()

    def countdown(self):
        if self.timer_paused or not self.timer_running:
            return
        if self.time_left > 0:
            self.time_left -= 1
            self.progress.set(self.time_left / 60)
            self.update_timer_label()
            self.timer_id = self.root.after(1000, self.countdown)
        else:
            self.timer_running = False
            self.next_question(auto=True)

    def cancel_timer(self):
        if self.timer_running:
            if self.timer_id is not None:
                self.root.after_cancel(self.timer_id)
                self.timer_id = None
            self.timer_running = False

    def update_timer_label(self):
        self.timer_label.configure(text=f"Time left: {self.time_left}s")

    def next_question(self, auto=False):
        selected_answer = self.selected.get()
        if selected_answer:
            self.user_answers[self.index] = selected_answer

        self.index += 1
        if self.index < len(self.questions):
            self.show_question()
            self.question_picker.delete(0, 'end')
            self.question_picker.insert(0, str(self.index + 1))
        else:
            self.finish_exam()

    def jump_to_question(self):
        try:
            q_num = int(self.question_picker.get()) - 1
            if 0 <= q_num < len(self.questions):
                self.index = q_num
                self.show_question()
        except Exception:
            pass

    def finish_exam(self):
        self.cancel_timer()
        self.score = 0
        for i, q in enumerate(self.questions):
            if self.user_answers.get(i, "") == q.get("answer", ""):
                self.score += 1

        messagebox.showinfo("Exam Finished", f"Your score: {self.score}/{len(self.questions)} in {self.current_session}")

        pygame.mixer.quit()

        try:
            with open("score.txt", "a") as f:
                f.write(f"{self.current_session} - Score: {self.score}/{len(self.questions)}\n")
        except Exception as e:
            messagebox.showwarning("File Error", f"Could not save score: {e}")

        self.show_results_review()

    def show_results_review(self):
        review_win = ctk.CTkToplevel(self.root)
        review_win.geometry("600x600")
        review_win.title("Exam Results and Review")

        scrollable_frame = ctk.CTkScrollableFrame(review_win, width=580, height=580)
        scrollable_frame.pack(fill="both", expand=True, padx=10, pady=10)

        header = ctk.CTkLabel(scrollable_frame, text="Question Review", font=ctk.CTkFont(size=18, weight="bold"),
                              text_color=ctk.ThemeManager.theme["CTkLabel"]["text_color"])
        header.pack(pady=10)

        bg_color_light = ctk.ThemeManager.theme["CTkFrame"]["fg_color"]
        bg_color_alt = ctk.ThemeManager.theme["CTkFrame"]["fg_color"]

        for idx, question in enumerate(self.questions):
            bg_color = bg_color_light if idx % 2 == 0 else bg_color_alt
            frame = ctk.CTkFrame(scrollable_frame, fg_color=bg_color)
            frame.pack(fill="x", pady=5, padx=5)

            q_label = ctk.CTkLabel(frame, text=f"Q{idx + 1}: {question['question']}",
                                   wraplength=550, font=ctk.CTkFont(size=14, weight="bold"),
                                   text_color=ctk.ThemeManager.theme["CTkLabel"]["text_color"])
            q_label.pack(anchor="w")

            student_ans = self.user_answers.get(idx, "(Not Answered)")
            right_ans = question.get("answer", "(No answer)")

            correct = student_ans == right_ans
            color = "#58D68D" if correct else "#E74C3C"

            ans_label = ctk.CTkLabel(frame, text=f"Your answer: {student_ans}", text_color=color, wraplength=550)
            ans_label.pack(anchor="w", padx=10)

            right_label = ctk.CTkLabel(frame, text=f"Correct answer: {right_ans}",
                                      text_color=ctk.ThemeManager.theme["CTkLabel"]["text_color"], wraplength=550)
            right_label.pack(anchor="w", padx=10)

        close_btn = ctk.CTkButton(review_win, text="Close", command=review_win.destroy)
        close_btn.pack(pady=15)

    def toggle_mute(self):
        self.is_muted = not self.is_muted
        self.mute_button.configure(text="Unmute" if self.is_muted else "Mute")

    def toggle_timer_pause(self):
        if self.timer_paused:
            self.timer_paused = False
            self.pause_button.configure(text="Pause Timer")
            self.countdown()
        else:
            self.timer_paused = True
            self.pause_button.configure(text="Resume Timer")
            if self.timer_id:
                self.root.after_cancel(self.timer_id)
                self.timer_id = None

    def show_answer(self):
        current_question = self.questions[self.index]
        correct_answer = current_question.get("answer", "No answer")
        messagebox.showinfo("Correct Answer", f"The correct answer is:\n{correct_answer}")

    def load_all_sessions(self):
        try:
            with open(resource_path("questions_by_session.json"), "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            else:
                messagebox.showerror("Data Error", "JSON data is not of expected dictionary type.")
                return {}
        except FileNotFoundError:
            messagebox.showwarning("File Not Found", "questions_by_session.json not found in application directory.")
            return {}


def main():
    root = ctk.CTk()
    root.withdraw()

    splash = SplashScreen(root)
    splash.focus_force()

    def start_app():
        splash.destroy()
        root.deiconify()
        app = ExamApp(root)

    root.after(10000, start_app)
    root.mainloop()


if __name__ == "__main__":
    main()