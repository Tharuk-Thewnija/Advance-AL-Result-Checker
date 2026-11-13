"""Keyboard activation and visible focus for CustomTkinter controls."""
import customtkinter as ctk


def _visible(widget):
    widget.update_idletasks()
    parent = widget.master
    while parent is not None:
        if isinstance(parent, ctk.CTkScrollableFrame):
            canvas = parent._parent_canvas
            top = widget.winfo_rooty() - parent.winfo_rooty()
            start = canvas.canvasy(0)
            if top < start or top + widget.winfo_height() > start + canvas.winfo_height():
                canvas.yview_moveto(max(0, top - 8) / max(1, parent.winfo_height()))
                parent.update_idletasks()
        parent = parent.master


class _KeyboardControl:
    def _enable_keyboard(self, action):
        # CustomTkinter delegates focus_set() to its native text label.
        for name in ('_canvas', '_bg_canvas'):
            canvas = getattr(self, name, None)
            if canvas is not None:
                canvas.configure(takefocus=0)
        self._text_label.configure(takefocus=lambda *_: int(self.cget('state') != 'disabled'),
                                   highlightthickness=1)

        def activate(_):
            if self.cget('state') != 'disabled':
                action()
            return 'break'

        self.bind('<KeyPress-space>', activate)
        self.bind('<Return>', activate)
        self.bind('<FocusIn>', lambda _: _visible(self))
        self._focus_colours()

    def _focus_colours(self):
        if getattr(self, '_text_label', None) is not None:
            self._text_label.configure(highlightcolor=self._apply_appearance_mode(('#2456C6', '#739EFF')),
                                       highlightbackground=self._apply_appearance_mode(self.cget('bg_color')))

    def _set_appearance_mode(self, mode):
        super()._set_appearance_mode(mode)
        self._focus_colours()


class KeyboardCheckBox(_KeyboardControl, ctk.CTkCheckBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._enable_keyboard(self.toggle)


class KeyboardButton(_KeyboardControl, ctk.CTkButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._enable_keyboard(self.invoke)


class KeyboardOptionMenu(_KeyboardControl, ctk.CTkOptionMenu):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._enable_keyboard(self._open_dropdown_menu)
