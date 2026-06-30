import os
import fitz
from PySide6 import QtWidgets, QtCore, QtGui
from ..theme import THEME_MGR
from .. import icons as _icons
from ..widgets import _HoverMixin


class _FirstPageButton(_HoverMixin, QtWidgets.QAbstractButton):
    """Кнопка «на першу сторінку» у статус-барі viewer — малює arrow_up через icons.draw()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._press = False
        self.setFixedSize(20, 20)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setToolTip("Перша сторінка")
        self._init_hover()

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self._press = True
            self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._press = False
        self.update()
        super().mouseReleaseEvent(e)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        t = THEME_MGR.get()
        if self._press:
            alpha = 230
        elif self._hover:
            alpha = 190
        else:
            alpha = int(t.statusbar_page_alpha)
        c = QtGui.QColor(t.nav_icon_inactive_color)
        c.setAlpha(alpha)
        _icons.draw(p, self.rect(), "arrow_up", c)
        p.end()

# 100 % zoom: 1 PDF point rendered as 1 screen pixel at 96 DPI
_SCALE_100   = 96.0 / 72.0   # ≈ 1.333
_DEFAULT_SCALE = _SCALE_100 * 1.25


class PageWidget(QtWidgets.QWidget):
    """Renders a single PDF page; handles rubber-band text selection."""

    page_clicked  = QtCore.Signal(object)
    cursor_moved  = QtCore.Signal(int, float, float)   # page_num, pdf_x, pdf_y
    cursor_left   = QtCore.Signal()

    def __init__(self, page_num: int, page: fitz.Page, scale: float, parent=None):
        super().__init__(parent)
        self._page_num      = page_num
        self._page          = page
        self._scale         = scale
        self._pixmap:       QtGui.QPixmap | None            = None
        self._words:        list[tuple[QtCore.QRectF, str]] = []
        self._sel_start:    QtCore.QPointF | None           = None
        self._sel_end:      QtCore.QPointF | None           = None
        self._highlighted:  list[QtCore.QRectF]             = []
        self._selected_text = ""
        self.setCursor(QtCore.Qt.IBeamCursor)
        self.setMouseTracking(True)
        self._render()

    # ── rendering ─────────────────────────────────────────────────────────────

    def _render(self):
        mat = fitz.Matrix(self._scale, self._scale)
        pix = self._page.get_pixmap(matrix=mat, alpha=False)
        img = QtGui.QImage(pix.samples, pix.width, pix.height,
                           pix.stride, QtGui.QImage.Format_RGB888)
        self._pixmap = QtGui.QPixmap.fromImage(img)
        self.setFixedSize(self._pixmap.size())
        self._load_words()

    def _load_words(self):
        self._words.clear()
        pr = self._page.rect
        pw = max(pr.width, 1.0)
        ph = max(pr.height, 1.0)
        sw = float(self._pixmap.width())
        sh = float(self._pixmap.height())
        for w in self._page.get_text("words"):
            x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
            self._words.append((
                QtCore.QRectF(x0 / pw * sw, y0 / ph * sh,
                              (x1 - x0) / pw * sw, (y1 - y0) / ph * sh),
                text,
            ))

    def rescale(self, scale: float):
        self._scale         = scale
        self._sel_start     = None
        self._sel_end       = None
        self._highlighted.clear()
        self._selected_text = ""
        self._render()
        self.update()

    # ── selection ─────────────────────────────────────────────────────────────

    def clear_selection(self):
        self._sel_start     = None
        self._sel_end       = None
        self._highlighted.clear()
        self._selected_text = ""
        self.update()

    @property
    def pixmap(self) -> QtGui.QPixmap | None:
        return self._pixmap

    @property
    def selected_text(self) -> str:
        return self._selected_text

    def _update_highlight(self):
        if not (self._sel_start and self._sel_end):
            self._highlighted.clear()
            self._selected_text = ""
            return
        rb   = QtCore.QRectF(self._sel_start, self._sel_end).normalized()
        hits = [(r, t) for r, t in self._words if r.intersects(rb)]
        hits.sort(key=lambda x: (round(x[0].top(), 1), x[0].left()))
        self._highlighted   = [r for r, _ in hits]
        self._selected_text = " ".join(t for _, t in hits)

    # ── cursor → PDF coordinates ───────────────────────────────────────────────

    def _emit_cursor(self, pos: QtCore.QPoint):
        if not self._pixmap:
            return
        pr   = self._page.rect
        pdf_x = pos.x() / float(self._pixmap.width())  * pr.width
        pdf_y = pos.y() / float(self._pixmap.height()) * pr.height
        self.cursor_moved.emit(self._page_num, pdf_x, pdf_y)

    # ── events ────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.page_clicked.emit(self)
            self._sel_start     = QtCore.QPointF(event.pos())
            self._sel_end       = self._sel_start
            self._highlighted.clear()
            self._selected_text = ""
            self.update()

    def mouseMoveEvent(self, event):
        self._emit_cursor(event.pos())
        if event.buttons() & QtCore.Qt.LeftButton and self._sel_start is not None:
            self._sel_end = QtCore.QPointF(event.pos())
            self._update_highlight()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._sel_start is not None:
            self._sel_end = QtCore.QPointF(event.pos())
            self._update_highlight()
            if self._selected_text:
                QtWidgets.QApplication.clipboard().setText(self._selected_text)
            self.update()

    def leaveEvent(self, event):
        self.cursor_left.emit()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        if self._pixmap:
            p.drawPixmap(0, 0, self._pixmap)
        if self._highlighted:
            sel_c = QtGui.QColor(THEME_MGR.get().selection_color)
            sel_c.setAlpha(90)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(sel_c)
            for rect in self._highlighted:
                p.drawRect(rect)
        elif self._sel_start and self._sel_end:
            sel_c = QtGui.QColor(THEME_MGR.get().selection_color)
            rb = QtCore.QRectF(self._sel_start, self._sel_end).normalized()
            sel_c.setAlpha(160)
            p.setPen(QtGui.QPen(sel_c, 1.0))
            sel_c.setAlpha(28)
            p.setBrush(sel_c)
            p.drawRect(rb)
        p.end()


class ScreenViewer(QtWidgets.QWidget):
    """Full-page PDF viewer with text selection, zoom, and clipboard copy."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc:          fitz.Document | None = None
        self._path:         str | None           = None
        self._scale:        float                = _DEFAULT_SCALE
        self._pages:        list[PageWidget]     = []
        self._current_page: int                  = 0
        self.setAcceptDrops(True)
        self._build_ui()

    # ── public API ────────────────────────────────────────────────────────────

    def load_pdf(self, path: str):
        self._clear_pages()
        if self._doc:
            try:
                self._doc.close()
            except Exception:
                pass
        self._path = path
        self._doc  = fitz.open(path)
        self._lbl_file.setText(os.path.basename(path))
        self._current_page = 0
        self._lbl_pages.setText(f"1/{self._doc.page_count}")
        self._lbl_cursor.setText("")
        self._scale = self._fit_scale()
        self._render_pages()

    def has_doc(self) -> bool:
        return self._doc is not None

    def close_doc(self):
        """Release the loaded PDF and rendered pages (e.g. before discarding the tab)."""
        self._clear_pages()
        if self._doc:
            try:
                self._doc.close()
            except Exception:
                pass
            self._doc = None
        self._path = None

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── scroll area ───────────────────────────────────────────────────────
        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)

        self._container = QtWidgets.QWidget()
        self._container.setStyleSheet("background: #2c2f3d;")
        self._vbox = QtWidgets.QVBoxLayout(self._container)
        self._vbox.setContentsMargins(20, 20, 20, 20)
        self._vbox.setSpacing(16)
        self._vbox.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
        self._scroll.setWidget(self._container)
        self._scroll.viewport().installEventFilter(self)
        self._scroll.verticalScrollBar().valueChanged.connect(self._update_current_page)

        root.addWidget(self._scroll, 1)

        # ── status bar (bottom) ───────────────────────────────────────────────
        sb = QtWidgets.QWidget()
        sb.setFixedHeight(28)
        sb.setStyleSheet(
            "QWidget { background: #191b21; border-top: 1px solid #2a3045; }"
        )
        sbl = QtWidgets.QHBoxLayout(sb)
        sbl.setContentsMargins(14, 0, 14, 0)
        sbl.setSpacing(0)

        self._lbl_file = QtWidgets.QLabel("Відкрийте PDF для перегляду")
        self._lbl_file.setStyleSheet(
            "color: rgba(255,255,255,0.65); font-size: 12px;"
            " background: transparent; border: none;"
        )
        sbl.addWidget(self._lbl_file, 1)

        _sep1 = QtWidgets.QFrame()
        _sep1.setFrameShape(QtWidgets.QFrame.VLine)
        _sep1.setStyleSheet("color: rgba(255,255,255,0.12); background: transparent; border: none;")
        _sep1.setFixedWidth(1)
        sbl.addSpacing(12)
        sbl.addWidget(_sep1)
        sbl.addSpacing(12)

        self._btn_first_page = _FirstPageButton()
        self._btn_first_page.clicked.connect(lambda: self._scroll_to_page(0))
        sbl.addWidget(self._btn_first_page)
        sbl.addSpacing(6)

        self._lbl_pages = QtWidgets.QLabel("")
        self._lbl_pages.setStyleSheet(
            "color: rgba(255,255,255,0.45); font-size: 12px;"
            " background: transparent; border: none;"
        )
        self._lbl_pages.setFixedWidth(52)
        self._lbl_pages.setAlignment(QtCore.Qt.AlignCenter)
        sbl.addWidget(self._lbl_pages)

        _sep2 = QtWidgets.QFrame()
        _sep2.setFrameShape(QtWidgets.QFrame.VLine)
        _sep2.setStyleSheet("color: rgba(255,255,255,0.12); background: transparent; border: none;")
        _sep2.setFixedWidth(1)
        sbl.addSpacing(12)
        sbl.addWidget(_sep2)
        sbl.addSpacing(12)

        self._lbl_cursor = QtWidgets.QLabel("")
        self._lbl_cursor.setStyleSheet(
            "color: rgba(255,255,255,0.35); font-size: 11px;"
            " background: transparent; border: none;"
        )
        self._lbl_cursor.setFixedWidth(130)
        self._lbl_cursor.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        sbl.addWidget(self._lbl_cursor)

        self._status_bar = sb
        root.addWidget(sb)
        self.apply_theme()

    # ── theme ─────────────────────────────────────────────────────────────────

    def apply_theme(self):
        t = THEME_MGR.get()

        # status bar background + border
        self._status_bar.setStyleSheet(
            f"QWidget {{ background: {t.bg_sidebar};"
            f" border-top: 1px solid {t.bg_border}; }}"
        )

        # status bar label colors
        fa = t.statusbar_file_alpha / 255
        pa = t.statusbar_page_alpha / 255
        ca = t.statusbar_cursor_alpha / 255
        self._lbl_file.setStyleSheet(
            f"color: rgba(255,255,255,{fa:.3f}); font-size: 12px;"
            " background: transparent; border: none;"
        )
        self._lbl_pages.setStyleSheet(
            f"color: rgba(255,255,255,{pa:.3f}); font-size: 12px;"
            " background: transparent; border: none;"
        )
        self._lbl_cursor.setStyleSheet(
            f"color: rgba(255,255,255,{ca:.3f}); font-size: 11px;"
            " background: transparent; border: none;"
        )

        # viewer scroll area + page container
        ha = min(1.0, t.scrollbar_alpha / 255)
        ha2 = min(1.0, ha * 2.1)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: {t.viewer_bg}; border: none; }}
            QScrollBar:vertical {{
                width: 8px; background: transparent; border: none; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255,255,255,{ha:.3f});
                border-radius: 4px; min-height: 28px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(255,255,255,{ha2:.3f});
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
            QScrollBar:horizontal {{
                height: 8px; background: transparent; border: none; margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: rgba(255,255,255,{ha:.3f});
                border-radius: 4px; min-width: 28px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: rgba(255,255,255,{ha2:.3f});
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
        """)
        self._container.setStyleSheet(f"background: {t.viewer_bg};")

        # trigger repaint on pages (for selection color change)
        for pw in self._pages:
            pw.update()

    # ── pages ─────────────────────────────────────────────────────────────────

    def _clear_pages(self):
        for pw in self._pages:
            pw.deleteLater()
        self._pages.clear()

    def _render_pages(self):
        self._clear_pages()
        if not self._doc:
            return
        for i in range(self._doc.page_count):
            page = self._doc.load_page(i)
            pw   = PageWidget(i, page, self._scale)
            pw.page_clicked.connect(self._on_page_clicked)
            pw.cursor_moved.connect(self._on_cursor_moved)
            pw.cursor_left.connect(self._on_cursor_left)

            shadow = QtWidgets.QGraphicsDropShadowEffect(pw)
            shadow.setBlurRadius(18)
            shadow.setOffset(2, 4)
            shadow.setColor(QtGui.QColor(0, 0, 0, 110))
            pw.setGraphicsEffect(shadow)

            self._vbox.addWidget(pw, alignment=QtCore.Qt.AlignHCenter)
            self._pages.append(pw)

    def _on_page_clicked(self, source: PageWidget):
        for pw in self._pages:
            if pw is not source:
                pw.clear_selection()

    def _scroll_to_page(self, page_num: int):
        if not self._pages or page_num < 0 or page_num >= len(self._pages):
            return
        pw = self._pages[page_num]
        self._scroll.verticalScrollBar().setValue(pw.pos().y())

    # ── current page tracking ─────────────────────────────────────────────────

    def _update_current_page(self):
        if not self._pages or not self._doc:
            return
        vp_mid = (self._scroll.verticalScrollBar().value()
                  + self._scroll.viewport().height() / 2)
        best = 0
        for i, pw in enumerate(self._pages):
            if pw.pos().y() <= vp_mid:
                best = i
            else:
                break
        self._current_page = best
        self._lbl_pages.setText(f"{best + 1}/{self._doc.page_count}")

    # ── cursor coordinates ────────────────────────────────────────────────────

    def _on_cursor_moved(self, page_num: int, pdf_x: float, pdf_y: float):
        self._lbl_cursor.setText(f"x {pdf_x:.1f}  y {pdf_y:.1f} pt")

    def _on_cursor_left(self):
        self._lbl_cursor.setText("")

    # ── zoom ──────────────────────────────────────────────────────────────────

    def _fit_scale(self) -> float:
        vw = self._scroll.viewport().width()
        if vw < 100:
            vw = 900
        if not self._doc:
            return _DEFAULT_SCALE
        pdf_w = max(self._doc.load_page(0).rect.width, 1.0)
        return max(0.2, (vw - 56) / pdf_w)

    def _zoom_in(self):
        self._apply_scale(self._scale * 1.25)

    def _zoom_out(self):
        self._apply_scale(self._scale / 1.25)

    def _zoom_fit(self):
        self._apply_scale(self._fit_scale())

    def _apply_scale(self, new_scale: float):
        new_scale = max(0.15, min(new_scale, 10.0))
        if abs(new_scale - self._scale) < 0.001:
            return
        self._scale = new_scale
        for pw in self._pages:
            pw.rescale(new_scale)

    # ── print ─────────────────────────────────────────────────────────────────

    def print_document(self):
        if not self._doc:
            return
        from PySide6.QtPrintSupport import QPrinter, QPrintDialog
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self._do_print(printer)

    def print_preview(self):
        if not self._doc:
            return
        from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
        printer = QPrinter(QPrinter.HighResolution)
        preview = QPrintPreviewDialog(printer, self)
        preview.paintRequested.connect(self._do_print)
        preview.exec()

    def _do_print(self, printer):
        from PySide6.QtPrintSupport import QPrinter
        painter = QtGui.QPainter()
        if not painter.begin(printer):
            return
        page_rect = printer.pageRect(QPrinter.DevicePixel).toRect()
        for i, pw in enumerate(self._pages):
            if i > 0:
                printer.newPage()
            if pw.pixmap:
                scaled = pw.pixmap.scaled(
                    page_rect.size(),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                x = (page_rect.width()  - scaled.width())  // 2
                y = (page_rect.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
        painter.end()

    # ── events ────────────────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(
                u.toLocalFile().lower().endswith(".pdf")
                for u in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls()
                 if u.toLocalFile().lower().endswith(".pdf")]
        if paths:
            self.load_pdf(paths[0])
            event.acceptProposedAction()
        else:
            event.ignore()

    def _handle_nav_key(self, key: int) -> bool:
        n = len(self._pages)
        if key == QtCore.Qt.Key_Home:
            self._scroll_to_page(0)
        elif key == QtCore.Qt.Key_End:
            self._scroll_to_page(n - 1)
        elif key == QtCore.Qt.Key_PageDown:
            self._scroll_to_page(min(self._current_page + 1, n - 1))
        elif key == QtCore.Qt.Key_PageUp:
            self._scroll_to_page(max(self._current_page - 1, 0))
        else:
            return False
        return True

    def eventFilter(self, obj, event):
        if obj is self._scroll.viewport():
            t = event.type()
            if t == QtCore.QEvent.Wheel and event.modifiers() & QtCore.Qt.ControlModifier:
                if event.angleDelta().y() > 0:
                    self._zoom_in()
                else:
                    self._zoom_out()
                return True
            elif t == QtCore.QEvent.KeyPress:
                if self._handle_nav_key(event.key()):
                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        key = event.key()
        if event.modifiers() & QtCore.Qt.ControlModifier:
            if key == QtCore.Qt.Key_C:
                for pw in self._pages:
                    if pw.selected_text:
                        QtWidgets.QApplication.clipboard().setText(pw.selected_text)
                        break
            elif key == QtCore.Qt.Key_A:
                if self._doc:
                    parts = [
                        self._doc.load_page(i).get_text("text")
                        for i in range(self._doc.page_count)
                    ]
                    QtWidgets.QApplication.clipboard().setText("\n".join(parts))
        elif not self._handle_nav_key(key):
            super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self._doc and not self._pages:
            self._scale = self._fit_scale()
            self._render_pages()


# ── Tabbed viewer (Chrome-style tabs, one per open PDF) ────────────────────────

def _blend(c1: QtGui.QColor, c2: QtGui.QColor, t: float) -> QtGui.QColor:
    t = max(0.0, min(1.0, t))
    return QtGui.QColor(
        int(c1.red()   + (c2.red()   - c1.red())   * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue()  + (c2.blue()  - c1.blue())  * t),
    )


class _ChromeTabBar(QtWidgets.QTabBar):
    """Fully custom-painted tab bar — bypasses the native Windows style entirely
    (it ignores most QSS on QTabBar), matching the rest of the app's
    custom-painted widgets (NavButton, DropZone, ...).
    """

    _TAB_H      = 34
    _PREF_W     = 200   # natural width while there's room
    _MIN_W      = 64    # floor width once tabs must squeeze to fit (Chrome-like)
    _PLUS_W     = 30
    _RADIUS     = 8
    _PAD_L      = 12
    _CLOSE_SZ   = 14
    _CLOSE_GAP  = 8
    _PAD_R      = 10
    _SWAP_OVERLAP = 0.60   # swap as soon as the dragged tab has covered this much of a neighbor

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setExpanding(False)
        self.setDrawBase(False)
        self.setMovable(False)   # we drive dragging ourselves for the Chrome-style overlap slide
        self.setCursor(QtCore.Qt.PointingHandCursor)
        # native styles reserve a few px of margin around tabs beyond tabSizeHint,
        # which left a thin bar_bg sliver below the tab shapes — pin the bar's own
        # height so there's nothing left uncovered between tabs and the content below
        self.setFixedHeight(self._TAB_H)
        self._hover_progress: dict[int, float] = {}
        self._hovered_index = -1
        self._close_rects: dict[int, QtCore.QRect] = {}
        self._anim_timer = QtCore.QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick)
        self.tabMoved.connect(self._keep_plus_last)

        self._drag_idx = -1
        self._drag_offset = 0.0
        self._press_x = 0.0

    # ── sizing ────────────────────────────────────────────────────────────────

    def _real_count(self) -> int:
        return sum(1 for i in range(self.count()) if self.tabData(i) != "plus")

    def tabSizeHint(self, index):
        if self.tabData(index) == "plus":
            return QtCore.QSize(self._PLUS_W, self._TAB_H)
        n = self._real_count()
        available = max(0, self.width() - self._PLUS_W)
        even_w = available / n if n else self._PREF_W
        w = max(self._MIN_W, min(self._PREF_W, even_w))
        return QtCore.QSize(int(w), self._TAB_H)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # tab widths are a function of bar width (Chrome-like shrink-to-fit) — force relayout
        self.updateGeometry()
        self.update()

    # ── keep the "+" tab pinned to the end when reordering ───────────────────

    def _keep_plus_last(self, *_):
        for i in range(self.count() - 1):
            if self.tabData(i) == "plus":
                self.moveTab(i, self.count() - 1)
                break

    # ── hover tracking / animation ───────────────────────────────────────────

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        idx = self.tabAt(pos)
        if idx != self._hovered_index:
            self._hovered_index = idx
            self._anim_timer.start()

        if self._drag_idx != -1:
            self._drag_offset = pos.x() - self._press_x
            self._maybe_swap()
            self._clamp_drag_offset()
            self.update()
            return
        super().mouseMoveEvent(event)

    def _clamp_drag_offset(self):
        rect = self.tabRect(self._drag_idx)
        left_bound = 0
        right_bound = self.width() - self._PLUS_W
        min_offset = left_bound - rect.x()
        max_offset = right_bound - rect.right()
        self._drag_offset = max(min_offset, min(max_offset, self._drag_offset))

    def leaveEvent(self, event):
        self._hovered_index = -1
        self._anim_timer.start()
        super().leaveEvent(event)

    def _tick(self):
        settled = True
        for i in range(self.count()):
            target = 1.0 if i == self._hovered_index else 0.0
            cur = self._hover_progress.get(i, 0.0)
            if abs(cur - target) > 0.01:
                cur += (target - cur) * 0.35
                self._hover_progress[i] = cur
                settled = False
            elif cur != target:
                self._hover_progress[i] = target
        self.update()
        if settled:
            self._anim_timer.stop()

    # ── mouse press / release (close-button hit test + custom drag-reorder) ──

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            idx = self.tabAt(event.pos())
            rect = self._close_rects.get(idx)
            if rect and rect.contains(event.pos()) and self.tabData(idx) != "plus":
                self.tabCloseRequested.emit(idx)
                return
            if idx != -1 and self.tabData(idx) != "plus":
                self.setCurrentIndex(idx)
                self._drag_idx = idx
                self._press_x = event.position().toPoint().x()
                self._drag_offset = 0.0
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_idx != -1:
            self._drag_idx = -1
            self._drag_offset = 0.0
            self.update()
            return
        super().mouseReleaseEvent(event)

    def _tab_draw_rect(self, index: int) -> QtCore.QRect:
        rect = self.tabRect(index)
        if index == self._drag_idx and self._drag_offset:
            rect = rect.translated(int(self._drag_offset), 0)
        return rect

    def _maybe_swap(self):
        # _drag_offset is recomputed every move from (mouse_x - _press_x). After a swap the
        # dragged tab's nominal slot jumps by the neighbor's width, so _press_x must absorb
        # that jump too — otherwise next frame's offset is computed against a stale reference
        # and the tab "teleports", cascading swaps all the way to one end of the bar.
        cur = self._drag_idx
        rect = self.tabRect(cur)
        w = rect.width()
        visual_left = rect.x() + self._drag_offset

        if cur > 0 and self.tabData(cur - 1) != "plus":
            left_rect = self.tabRect(cur - 1)
            overlap = left_rect.right() - visual_left   # how far we've crossed into the left neighbor
            if overlap > w * self._SWAP_OVERLAP:
                shift = rect.x() - left_rect.x()
                self.moveTab(cur, cur - 1)
                self._drag_idx = cur - 1
                self._drag_offset += shift
                self._press_x -= shift
                return

        n_real = self._real_count()
        if cur < n_real - 1:
            right_rect = self.tabRect(cur + 1)
            overlap = (visual_left + w) - right_rect.x()   # how far we've crossed into the right neighbor
            if overlap > w * self._SWAP_OVERLAP:
                shift = right_rect.x() - rect.x()
                self.moveTab(cur, cur + 1)
                self._drag_idx = cur + 1
                self._drag_offset -= shift
                self._press_x += shift
                return

    # ── painting ──────────────────────────────────────────────────────────────

    @staticmethod
    def _rounded_top_path(rect: QtCore.QRect, radius: int) -> QtGui.QPainterPath:
        r = QtCore.QRectF(rect)
        path = QtGui.QPainterPath()
        path.moveTo(r.left(), r.bottom())
        path.lineTo(r.left(), r.top() + radius)
        path.quadTo(r.left(), r.top(), r.left() + radius, r.top())
        path.lineTo(r.right() - radius, r.top())
        path.quadTo(r.right(), r.top(), r.right(), r.top() + radius)
        path.lineTo(r.right(), r.bottom())
        path.closeSubpath()
        return path

    def _paint_tab_content(self, p: QtGui.QPainter, i: int, rect: QtCore.QRect,
                            selected: bool, hover: float) -> None:
        if self.tabData(i) == "plus":
            alpha = 0.55 + 0.35 * hover
            p.setPen(QtGui.QColor(255, 255, 255, int(255 * alpha)))
            font = self.font()
            font.setPixelSize(15)
            font.setWeight(QtGui.QFont.DemiBold)
            p.setFont(font)
            p.drawText(rect, QtCore.Qt.AlignCenter, "+")
            return

        close_rect = QtCore.QRect(
            rect.right() - self._PAD_R - self._CLOSE_SZ,
            rect.center().y() - self._CLOSE_SZ // 2,
            self._CLOSE_SZ, self._CLOSE_SZ,
        )
        self._close_rects[i] = close_rect

        text_rect = QtCore.QRect(
            rect.left() + self._PAD_L, rect.top(),
            close_rect.left() - self._CLOSE_GAP - (rect.left() + self._PAD_L),
            rect.height(),
        )
        text_alpha = 0.95 if selected else (0.80 + 0.15 * hover)
        p.setPen(QtGui.QColor(255, 255, 255, int(255 * text_alpha)))
        font = self.font()
        font.setWeight(QtGui.QFont.DemiBold if selected else QtGui.QFont.Normal)
        p.setFont(font)
        fm = QtGui.QFontMetrics(font)
        elided = fm.elidedText(self.tabText(i), QtCore.Qt.ElideRight, max(0, text_rect.width()))
        p.drawText(text_rect, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, elided)

        close_alpha = 0.85 if selected else (0.55 + 0.30 * hover)
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, int(255 * close_alpha)), 1.4)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        m = 4
        cr = close_rect.adjusted(m, m, -m, -m)
        p.drawLine(cr.topLeft(), cr.bottomRight())
        p.drawLine(cr.topRight(), cr.bottomLeft())

    def paintEvent(self, event):
        t = THEME_MGR.get()
        # bar/inactive sit a step above bg_sidebar but clearly below viewer_bg, so the active
        # tab (flat viewer_bg — the actual color behind the page thumbnails) reads as the
        # highlighted one and flows seamlessly into the document area beneath it
        bar_bg = QtGui.QColor(t.bg_sidebar).lighter(115)
        active_bg = QtGui.QColor(t.viewer_bg)
        inactive_bg = bar_bg
        hover_bg = QtGui.QColor(t.bg_sidebar).lighter(140)

        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.fillRect(self.rect(), bar_bg)

        selected_idx = self.currentIndex()
        self._close_rects.clear()

        # layers 1+2: every non-selected tab — background, then its own text/close — fully
        # under the selected tab so nothing of theirs can show through it
        for i in range(self.count()):
            if i == selected_idx:
                continue
            rect = self._tab_draw_rect(i)
            if not rect.isValid():
                continue
            hover = self._hover_progress.get(i, 0.0)
            p.fillPath(self._rounded_top_path(rect, self._RADIUS), _blend(inactive_bg, hover_bg, hover))
            self._paint_tab_content(p, i, rect, False, hover)

        # layers 3+4: the selected (possibly dragged) tab, painted as one opaque unit on top
        # of everything else — background bleeds into neighbors by one radius so its rounded
        # corners overlap theirs (otherwise the two curves leave a notch of bar_bg showing
        # through at the seam), and while dragging this rect is already offset, so the tab
        # visually slides and fully covers whatever neighbor it overlaps (no see-through text)
        if 0 <= selected_idx < self.count():
            rect = self._tab_draw_rect(selected_idx)
            if rect.isValid():
                hover = self._hover_progress.get(selected_idx, 0.0)
                bleed = rect.adjusted(-self._RADIUS, 0, self._RADIUS, 0)
                p.fillPath(self._rounded_top_path(bleed, self._RADIUS), active_bg)
                self._paint_tab_content(p, selected_idx, rect, True, hover)
        p.end()


class PdfViewerTabs(QtWidgets.QWidget):
    """Holds one ScreenViewer per open PDF, switchable via a Chrome-like tab bar.

    The "+" control is a real, permanent last tab (no close button) rather than
    a corner widget, so it sits flush against the last document tab like in
    Chrome instead of floating at the far edge of the bar. The tab bar is
    custom-painted (see _ChromeTabBar) since the native Windows style largely
    ignores QSS on QTabBar.
    """

    all_closed = QtCore.Signal()   # emitted when the last document tab is closed

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QtWidgets.QTabWidget()
        self._tabs.setTabBar(_ChromeTabBar())
        self._tabs.setDocumentMode(True)
        self._tabs.setTabsClosable(False)   # close glyph is custom-painted/hit-tested
        # movability is set on the bar itself (_ChromeTabBar.__init__) — don't override it here
        self._tabs.tabBar().tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._on_current_changed)
        root.addWidget(self._tabs)

        self._add_plus_tab()

    # ── public API ────────────────────────────────────────────────────────────

    def add_tab(self, path: str):
        for i in range(self._plus_index()):
            if self._tabs.widget(i)._path == path:
                self._tabs.setCurrentIndex(i)
                return
        viewer = ScreenViewer()
        viewer.setAcceptDrops(False)   # adding files goes through the "+" tab / drop zone
        viewer.load_pdf(path)
        idx = self._tabs.insertTab(self._plus_index(), viewer, os.path.basename(path))
        self._tabs.setTabToolTip(idx, path)
        self._tabs.setCurrentIndex(idx)

    def reset(self):
        while self._tabs.count() > 1:   # keep the trailing "+" tab
            w = self._tabs.widget(0)
            self._tabs.removeTab(0)
            w.close_doc()
            w.deleteLater()

    def paths(self) -> list[str]:
        return [self._tabs.widget(i)._path for i in range(self._plus_index())]

    def current_viewer(self) -> ScreenViewer | None:
        w = self._tabs.currentWidget()
        return w if isinstance(w, ScreenViewer) else None

    def apply_theme(self):
        t = THEME_MGR.get()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: {t.viewer_bg}; top: -1px; }}
            QTabBar QToolButton {{
                background: {t.bg_hover};
                border: none;
                border-radius: 5px;
                min-width: 28px;
                min-height: 28px;
                margin: 2px 3px;
            }}
            QTabBar QToolButton:hover {{ background: {t.bg_border}; }}
            QTabBar QToolButton:pressed {{ background: {t.accent}; }}
            QTabBar QToolButton::left-arrow {{ image: none; border-right: 6px solid white; border-top: 5px solid transparent; border-bottom: 5px solid transparent; width: 0; height: 0; }}
            QTabBar QToolButton::right-arrow {{ image: none; border-left: 6px solid white; border-top: 5px solid transparent; border-bottom: 5px solid transparent; width: 0; height: 0; }}
        """)
        self._tabs.tabBar().update()
        for i in range(self._plus_index()):
            self._tabs.widget(i).apply_theme()

    # ── internals ─────────────────────────────────────────────────────────────

    def _plus_index(self) -> int:
        return self._tabs.count() - 1

    def _add_plus_tab(self):
        idx = self._tabs.addTab(QtWidgets.QWidget(), "+")
        self._tabs.setTabToolTip(idx, "Відкрити ще один PDF")
        self._tabs.tabBar().setTabData(idx, "plus")

    def _close_tab(self, index: int):
        if index == self._plus_index():
            return
        w = self._tabs.widget(index)
        self._tabs.removeTab(index)
        w.close_doc()
        w.deleteLater()
        if self._tabs.count() == 1:   # only the "+" tab is left
            self.all_closed.emit()

    def _on_current_changed(self, index: int):
        if index != self._plus_index() or self._tabs.count() <= 1:
            return
        self._tabs.blockSignals(True)
        self._tabs.setCurrentIndex(index - 1)
        self._tabs.blockSignals(False)
        self._on_add_clicked()

    def _on_add_clicked(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Відкрити PDF", "", "PDF files (*.pdf)"
        )
        for p in paths:
            self.add_tab(p)
