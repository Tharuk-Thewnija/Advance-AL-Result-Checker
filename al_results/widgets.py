"""Keyboard activation and visible focus for CustomTkinter controls."""
import customtkinter as ctk


class ResponsiveScrollbar(ctk.CTkScrollbar):
    """Coalesce CTk redraw requests without changing scroll position updates.

    CTk 6's drawing method flushes Tk's idle queue. Running that method inside
    every canvas scroll callback causes nested layout work during resizing.
    Coalesced painting avoids that forced flush and leaves event processing to Tk.
    """
    def __init__(self, *args, **kwargs):
        self._draw_job = None
        self._needs_color_update = False
        self._render_destroyed = False
        super().__init__(*args, **kwargs)

    def _draw(self, no_color_updates=False):
        if self._render_destroyed:
            return
        self._needs_color_update |= not no_color_updates
        if self._draw_job is None:
            self._draw_job = self.after(16, self._flush_draw)

    def _flush_draw(self):
        self._draw_job = None
        color_update = self._needs_color_update
        self._needs_color_update = False
        # Match CTk 6's drawing contract, but let Tk finish layout/painting in
        # its own event loop rather than calling update_idletasks inside paint.
        ctk.CTkBaseClass._draw(self, no_color_updates=not color_update)
        start, end = self._get_scrollbar_values_for_minimum_pixel_size()
        recolor = self._draw_engine.draw_rounded_scrollbar(
            self._apply_widget_scaling(self._current_width),
            self._apply_widget_scaling(self._current_height),
            self._apply_widget_scaling(self._corner_radius),
            self._apply_widget_scaling(self._border_spacing), start, end, self._orientation,
        )
        if color_update or recolor:
            track = self._bg_color if self._fg_color == 'transparent' else self._fg_color
            thumb = self._button_hover_color if self._hover_state else self._button_color
            for tag, color in (('border_parts', track), ('scrollbar_parts', thumb)):
                color = self._apply_appearance_mode(color)
                self._canvas.itemconfig(tag, fill=color, outline=color)
            self._canvas.configure(bg=self._apply_appearance_mode(track))

    def set(self, start_value, end_value):
        start, end = float(start_value), float(end_value)
        if (start, end) != (self._start_value, self._end_value):
            self._start_value, self._end_value = start, end
            self._draw()

    def destroy(self):
        if self._render_destroyed:
            return
        self._render_destroyed = True
        if self._draw_job is not None:
            self.after_cancel(self._draw_job)
            self._draw_job = None
        super().destroy()


class ResponsiveScrollableFrame(ctk.CTkScrollableFrame):
    """Keep CTk's layout/theme behavior, with a locally optimized scrollbar."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        old = self._scrollbar
        colors = {key: old.cget(key) for key in
                  ('fg_color', 'bg_color', 'button_color', 'button_hover_color')}
        self._scrollbar = ResponsiveScrollbar(
            self._parent_frame, orientation=self._orientation,
            command=self._parent_canvas.yview if self._orientation == 'vertical' else self._parent_canvas.xview,
            **colors,
        )
        old.destroy()
        direction = 'yscrollcommand' if self._orientation == 'vertical' else 'xscrollcommand'
        self._parent_canvas.configure(**{direction: self._scrollbar.set})
        self._create_grid()


class ResponsiveTextbox(ctk.CTkTextbox):
    """Use the same coalesced drawing for the log's two internal scrollbars."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for axis, orientation in (('x', 'horizontal'), ('y', 'vertical')):
            attribute = f'_{axis}_scrollbar'
            old = getattr(self, attribute)
            options = {key: old.cget(key) for key in (
                'width', 'height', 'corner_radius', 'border_spacing', 'fg_color',
                'bg_color', 'button_color', 'button_hover_color',
            )}
            scrollbar = ResponsiveScrollbar(
                self, orientation=orientation, command=getattr(self._textbox, f'{axis}view'), **options,
            )
            scrollbar.set(*old.get())
            old.destroy()
            setattr(self, attribute, scrollbar)
            self._textbox.configure(**{f'{axis}scrollcommand': scrollbar.set})
        self._create_grid_for_text_and_scrollbars(re_grid_x_scrollbar=True, re_grid_y_scrollbar=True)


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
            self._text_label.configure(
                highlightcolor=self._apply_appearance_mode(('#5941D6', '#8E7BFF')),
                highlightbackground=self._apply_appearance_mode(self.cget('bg_color')),
            )

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
