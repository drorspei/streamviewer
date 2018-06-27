#!/usr/bin/python

import os
import signal
import sys
import Tkinter
import select
import Queue
import time
import re
from threading import Event, Thread


class ThreadSafeConsole(Tkinter.Text):
    def __init__(self, searchptr, master, **options):
        Tkinter.Text.__init__(self, master, **options)
        self.searchptr = searchptr
        self.last_search = ''
        self.queue = Queue.Queue()
        self.update_me()
    def write(self, line):
        self.queue.put(line)
    def clear(self):
        self.queue.put(None)
    def update_me(self):
        cursor_at_end = self.compare('end-1c linestart', '==', 'insert linestart')
        lines = []
        try:
            start = time.time()
            while time.time() - start < 0.01:
                line = self.queue.get_nowait()
                if line is None:
                    lines = ['']
                    self.delete(1.0, Tkinter.END)
                else:
                    lines.append(line)
        except Queue.Empty:
            pass

        if lines:
            start_highlight = self.index(Tkinter.END)
            if self.compare('end-1c linestart', '==', 'end linestart'):
                self.insert(Tkinter.END, '\n')
            self.insert(Tkinter.END, '\n'.join(lines))

            s = self.searchptr[0]
            if s.startswith('%re '):
                s, regexp, nocase = s[4:], True, 0
            else:
                nocase = 1
                s = s.lower()
                regexp = False

            self.last_search = s
            self.highlight_pattern(s, 'searchtag', start_highlight, regexp=regexp, nocase=nocase)
            
            if cursor_at_end:
                self.see('end-1c linestart')
            self.update_idletasks()

        self.after(25, self.update_me)

    def highlight_pattern(self, pattern, tag, start="1.0", end="end",
                          regexp=False, nocase=0):
        '''Apply the given tag to all text that matches the given pattern

        If 'regexp' is set to True, pattern will be treated as a regular
        expression according to Tcl's regular expression syntax.
        '''
        if pattern != self.last_search:
            return

        start_time = time.time()
        start = self.index(start)
        end = self.index(end)
        self.mark_set("matchStart", end)
        self.mark_set("matchEnd", end)
        self.mark_set("searchLimit", start)

        count = Tkinter.IntVar()
        while True:
            index = self.search(pattern, "matchStart", "searchLimit",
                                count=count, regexp=regexp, nocase=nocase, backwards=True)
            if index == "": break
            if count.get() == 0: break # degenerate pattern which matches zero-length strings
            self.mark_set("matchStart", index)
            self.mark_set("matchEnd", "%s+%sc" % (index, count.get()))
            self.tag_add(tag, "matchStart", "matchEnd")

            if time.time() - start_time > 0.01:
                self.after(25, self.highlight_pattern, pattern, tag, start, index, regexp, nocase)
                return


def matchline(p, s):
    if p.startswith('%re '):
        return re.search(p[4:], s) is not None
    else:
        return p.lower() in s.lower()


def addlines(searchptr, text, event):
    lines = None, None
    last_search = ''
    
    while not event.is_set():
        new_search = searchptr[0]
        if new_search != last_search:
            s = []
            head = lines
            while head[0] is not None:
                head, tail = head
                if matchline(new_search, tail):
                    s.append(tail)
            s = '\n'.join(s[::-1])

            text.clear()
            text.write(s)
            last_search = new_search

        try:
            sel = select.select([sys.stdin], [], [], 0)[0]
        except ValueError:
            return
        if sys.stdin in sel:
            line = sys.stdin.readline()
            if not line:
                return
            else:
                line = line.rstrip()
                lines = lines, line

                if not last_search or matchline(last_search, line):
                    text.write(line)
        else:
            event.wait(0.01)


def streamview():
    root = Tkinter.Tk()

    text_options = {
        'name': 'text',
        'padx': 5,
        'highlightthickness': 0,
        'wrap': 'none',
    }
    if Tkinter.TkVersion >= 8.5:
        # Starting with tk 8.5 we have to set the new tabstyle option
        # to 'wordprocessor' to achieve the same display of tabs as in
        # older tk versions.
        text_options['tabstyle'] = 'wordprocessor'

    frame = Tkinter.Frame(root)
    frame.pack(fill=Tkinter.BOTH, expand=True)

    searchptr = ['']
    search_widget = []

    def set_searchptr(sv_):
        try:
            searchptr[0] = search_widget[0].get()
        except:
            pass

    text = ThreadSafeConsole(searchptr, frame, **text_options)
    text.config(foreground='#efefef', selectforeground='#000000', selectbackground='gray', background='#000000', 
                font='{dejavu sans mono} 14 normal', insertbackground='#2cfe34')
    text.insert(Tkinter.END, "Starting.....\n")
    text.pack(fill=Tkinter.BOTH, expand=True)
    text.tag_configure("searchtag", background="#444444")

    frame2 = Tkinter.Frame(root)
    frame2.pack(fill=Tkinter.X)

    sv = Tkinter.StringVar()
    sv.trace("w", lambda name, mode, sv_=sv: set_searchptr(sv_))
    search = Tkinter.Entry(frame2, textvariable=sv)
    search.config(**{'background': '#FFFFFF', 'font': '{dejavu sans mono} 14 normal'})
    search.pack(fill=Tkinter.X)
    search_widget.append(search)
    search.focus()

    event = Event()
    thread = Thread(target=addlines, args=(searchptr, text, event))

    def on_closing():
        root.destroy()

    try:
        thread.daemon = True
        thread.start()

        root.title('streamviewer')
        root.protocol("WM_DELETE_WINDOW", on_closing)
        root.mainloop()
    finally:
        event.set()


if __name__ == '__main__':
    streamview()
