from curses.textpad import Textbox, rectangle
import curses
import threading
import math

from data import logger
from data import conf
from data import recv_serial
from enums import KEYBOARD
from observe import Observer

from connect import Telnet
import features

conf.process_running = True


class Screen(object):
    """https://docs.python.org/3/howto/curses.html"""

    def __init__(self, port):

        self.top = 0

        self._window = None
        self.init_curses()

        self.port = port
        conf.port = port
        self._observer = Observer()
        recv_serial.add_observer(self._observer)

    def init_curses(self):

        self._window = curses.initscr()
        conf.window = self._window
        self._window.keypad(True)
        self._window.scrollok(True)

        curses.start_color()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)

        self._statusbar = StatusBar(self._window)

        self._window.clear()

        curses.noecho()
        curses.cbreak()
        curses.mousemask(-1)
        curses.start_color()

        self._menu = MenuEx(self._window)

    def keyboard_input(self):
        """这里获取输入并写入serialport"""
        logger.info("Screen.keyboard_input Run")
        while conf.process_running:
            ch = self._window.getch()

            if ch == curses.KEY_MOUSE:
                pass

            elif ch == KEYBOARD.Ctrl_A:  # Ctrl + A
                logger.info("Screen.keyboard_input: Menu.run()")
                self._menu.run()
                self._window.refresh()
            else:
                self.port.write(ch)

    def display_buffer(self):
        """作为显示主界面的循环"""
        pos = 1

        logger.info("Screen.display_buffer Run")
        while conf.process_running:
            y, x = self._window.getmaxyx()

            stream = self._observer.get(timeout=1)

            self._statusbar.display_statusbar(y, x)
            self._window.move(y-2, pos)

            for e in stream:
                if e == "\n":
                    # NOTE 加入capture
                    # logger.debug('%s' % self._window.instr(y-2, 1).rstrip())
                    if conf.capture:
                        conf.capture.info(self._window.instr(
                            y-2, 1).rstrip().decode())
                    self._window.scroll()
                    pos = 1

                elif (ord(e) == 8):  # 退格
                    if pos > 0:
                        pos -= 1
                    curses.killchar()
                    self._window.move(y-2, pos)

                elif (ord(e) == 7):  # 顶头
                    self._window.move(y-2, pos)
                    curses.flash()

                else:  # 实际内容
                    if pos >= x:
                        self._window.scroll()
                        pos = 1
                    self._window.addstr(y-2, pos, e)
                    pos += 1

            self._window.refresh()  # 需要重新刷新

    def thread_keyboard_input(self):
        return threading.Thread(target=self.keyboard_input, name='keyboard_input_thread')

    def thread_display_buffer(self):
        return threading.Thread(target=self.display_buffer, name='display_buffer_thread')

    def run(self):
        threads = []
        th1 = self.thread_keyboard_input()
        th2 = self.port.thread_loop_read()
        th3 = self.thread_display_buffer()
        threads.append(th1)
        threads.append(th2)
        threads.append(th3)

        for t in threads:
            t.setDaemon(True)
            t.start()

        for t in threads:
            try:
                t.join()
            except KeyboardInterrupt:
                pass

        curses.endwin()


def yxcenter(scr, text=""):
    '''
    Given a curses window and a string, return the x, y coordinates to pass to
    scr.addstr() for the provided text to be drawn in the horizontal and
    vertical center of the window.
    '''
    y, x = scr.getmaxyx()
    nx = (x // 2) - (len(text) // 2)
    ny = (y // 2) - (len(text.split('\n')) // 2)
    return ny, nx


class MenuEx:

    def __init__(self, window):
        """
        @_items
        {sortkey: [description, dirct_function]}
        """
        self._window = window
        self._menu = None
        self._options = {}

        self.max_long = 60

        self.add_item('t', 'connection Telnet turn on/off',
                      features.telnet, True)
        self.add_item('q', 'Quit Process', features.exit)
        self.add_item('c', 'Capture file', features.capture)

    def add_item(self, sortkey, description, dirct_func, quit_menu=False):
        """添加选项"""
        self._options[sortkey.upper()] = {
            'description': description, 'dirct_func': dirct_func, 'quit_menu': quit_menu}

    def getch(self):
        return self._menu.getch()

    def display_menu(self):
        buf = []
        buf.append("CollConsole Command Summary")
        buf.append("---------------------------")
        buf.append("")

        for k, v in self._options.items():
            desc = v['description']
            msg = desc + "." * (self.max_long-10-len(desc)) + k
            buf.append(msg)

        y, x = yxcenter(self._window)

        self._menu = curses.newwin(
            len(buf)+2, self.max_long, y-math.ceil(len(buf)/2), x-math.ceil(self.max_long/2))

        index = 1
        for i in buf:
            self._menu.addstr(index, 2, i)
            index += 1

        self._menu.border('|', '|', '-', '-', '+', '+', '+', '+')
        # self._menu.box()
        self._menu.refresh()

    def run(self):
        self.display_menu()

        while True:
            k = self.getch()
            if (k == KEYBOARD.Esc):
                self.quit()
                break

            # 执行指令
            elif chr(k).upper() in self._options.keys():
                item = self._options[chr(k).upper()]
                func = item['dirct_func']
                func()

                if item['quit_menu']:
                    self.quit()
                    break

    def quit(self):
        self._menu.clear()
        self._menu.refresh()


class StatusBar:
    """最底下的状态栏"""

    def __init__(self, window):
        self._window = window

    def get_status(self, x):
        msg = []

        msg.append('Ctrl + A to open menu')

        msg.append('%s %s' % (conf.serial_port, conf.baudrate))

        if conf.telnet:
            if conf.telnet_join:
                msg.append('Telnet Status: Connect')
            else:
                msg.append('Telnet Status: Listen')

        if conf.capture:
            msg.append('Capture Logging enable')

        msg = " | ".join(msg)
        _ = msg + " " * (x - len(msg))
        return _

    def display_statusbar(self, y, x):
        """添加状态栏"""
        self._window.setscrreg(0, y-2)
        self._window.attron(curses.color_pair(1))
        msg = self.get_status(x)
        self._window.addstr(y-1, 0, msg)
        self._window.attroff(curses.color_pair(1))


#
# 菜单面板
#
class DialogBox:

    def __init__(self):
        self._window = conf.window
        self._box = None
        self.controls = []
        self.length = 30

    def control_input(self, label: str):
        """输入控件"""
        c = ControlInput(label)
        self.add_control(c)

    def control_label(self, name: str):
        """标签控件"""
        c = ControlLabel(name)
        self.add_control(c)

    def control_button(self, buttons: list):
        """按钮控件"""
        c = ControlButton(buttons)
        self.add_control(c)

    def add_control(self, control):
        """添加控件，按照行来区分"""
        self.controls.append(control)

    def getch(self):
        return self._box.getch()

    def display(self):
        """如果有按钮，则返回按钮序列"""
        self.length = self.max_length(self.length) + 2
        height = len(self.controls) + 2

        ny, nx = yxcenter(conf.window)
        self._box = curses.newwin(height, self.length,
                                  ny-math.ceil(height/2),
                                  nx-math.ceil(self.length/2))
        index = 1
        for i in self.controls:
            i.box = self._box
            i.y, i.max_length = (index, self.length)
            i.display()
            index += 1

        self._box.box()
        self._box.refresh()

        self.inputs = {}

        select = 0
        for i in self.controls:
            if isinstance(i, ControlInput):
                self.inputs[i.name] = i.getch()

            if isinstance(i, ControlButton):
                select = i.getch()

        # 需要找self.input拿东西
        return select

    def quit(self):
        self._box.clear()
        self._box.refresh()

    def max_length(self, min_len: int):
        """比较长度，但是有个保底长度"""
        lens = []
        for i in self.controls:
            lens.append(len(i))

        lens.append(min_len)
        return max(lens)


class Control:
    def __init__(self):
        self.box = None
        self.x = 1
        self.y = 0
        self.max_length = 0

    def display(self):
        raise

    def __len__(self):
        raise


class ControlLabel(Control):
    def __init__(self, label):
        super().__init__()
        self._label = label

    def display(self):
        self.box.addstr(self.y, self.x, self._label)

    def __len__(self):
        return len(self._label)


class ControlButton(Control):
    def __init__(self, buttons):
        super().__init__()
        self.inputs = {}
        self.buttons = buttons
        self.freq = 0

    def create_button(self):
        num = len(self.buttons)
        once_length = (self.max_length - self.x) // num

        index = 0
        for i in self.buttons:
            space = (once_length - len(i)) // 2
            x = self.x + (index*once_length) + space

            if self.get_select() == index:
                self.box.attron(curses.color_pair(1))
                self.box.addstr(self.y, x, i)
                self.box.attroff(curses.color_pair(1))

            else:
                self.box.addstr(self.y, x, i)

            index += 1

    def display(self):
        self.create_button()

    def getch(self):
        curses.curs_set(0)
        while True:
            k = self.box.getch()
            if k == KEYBOARD.Enter:
                break

            else:
                # NOTE 需要加入颜色变换
                self.switch()
                self.create_button()

        curses.curs_set(1)
        return self.get_select()

    def switch(self):
        self.freq += 1
        return self.get_select()

    def get_select(self):
        _ = self.freq % len(self.buttons)
        return _

    def __len__(self):
        return 1


class ControlInput(Control):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self._label = " > "
        self._pos = len(self._label)

    @property
    def label(self):
        return self._label

    @label.setter
    def label(self, v):
        self._label = v + " > "
        self._pos = len(self._label)

    def display(self):
        self.box.addstr(self.y, self.x, self._label)

    def getstr(self):
        s = self.box.getstr(self.y, self._pos)
        logger.info('%s input -> %s' % (self.name, s))
        return s

    def getch(self):
        # 关于子窗口使用 derwin 还是 subwin
        # https://stackoverflow.com/questions/11234785/obscure-curses-error-message-when-creating-a-sub-window
        input_box = self.box.derwin(
            1, self.max_length - self._pos - 1, self.y, self._pos)

        input_textbox = Textbox(input_box)
        input_textbox.edit()
        logger.debug('cotrol input -> %s' % input_textbox.gather())
        return input_textbox.gather()

    def __len__(self):
        return 50