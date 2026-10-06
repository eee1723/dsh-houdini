"""Editable, read-only node browser example for a Houdini Python Panel.

Importing this module creates no widgets, callbacks, scene nodes or files.
The generated package supplies a thin .pypanel entry and this source module.
"""
import hou
from PySide6 import QtCore, QtGui, QtWidgets


class NodeReferencePanel(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.node_path = None
        layout = QtWidgets.QVBoxLayout(self)
        heading = QtWidgets.QHBoxLayout()
        heading.addWidget(QtWidgets.QLabel('参考节点'))
        self.path = QtWidgets.QLineEdit()
        self.path.setReadOnly(True)
        self.path.setPlaceholderText('选择 SOP 节点，查看参数结构')
        heading.addWidget(self.path, 1)
        self.chooser = hou.qt.NodeChooserButton()
        self.chooser.setNodeChooserFilter(hou.nodeTypeFilter.Sop)
        self.chooser.nodeSelected.connect(self.set_node)
        heading.addWidget(self.chooser)
        layout.addLayout(heading)
        self.search = hou.qt.SearchLineEdit()
        self.search.setPlaceholderText('筛选参数名称')
        layout.addWidget(self.search)
        self.model = QtGui.QStandardItemModel(self)
        self.model.setHorizontalHeaderLabels(['参数', '内部名', '类型'])
        self.filtered = QtCore.QSortFilterProxyModel(self)
        self.filtered.setSourceModel(self.model)
        self.filtered.setFilterKeyColumn(-1)
        self.filtered.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.search.textChanged.connect(self.filtered.setFilterFixedString)
        # QTreeView inherits the host theme. hou.qt.TreeView is H22-only and
        # would prevent this declared H21/H22 example from opening in H21.
        self.tree = QtWidgets.QTreeView()
        self.tree.setModel(self.filtered)
        self.tree.setRootIsDecorated(False)
        self.tree.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.tree.setColumnWidth(1, 100)
        layout.addWidget(self.tree, 1)
        self.status = QtWidgets.QLabel('只读浏览参数模板，不 cook 或修改节点。')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def set_node(self, node):
        self.model.removeRows(0, self.model.rowCount())
        self.node_path = None
        self.path.clear()
        if node is None:
            self.status.setText('选择 SOP 节点，或继续使用 Houdini 的节点选择器。')
            return
        if isinstance(node, str):
            node = hou.node(node)
        if node is None or node.type().category() != hou.sopNodeTypeCategory():
            self.status.setText('请选择 SOP 节点。')
            return
        self.node_path = node.path()
        self.path.setText(self.node_path)
        self.chooser.setNodeChooserInitialNode(node)
        count = 0
        pending = list(node.parmTemplateGroup().entries())
        while pending and count < 512:
            template = pending.pop(0)
            if isinstance(template, hou.FolderParmTemplate):
                pending[0:0] = list(template.parmTemplates())
                continue
            items = [QtGui.QStandardItem(text) for text in
                (template.label(), template.name(), template.type().name())]
            for item in items:
                item.setToolTip(item.text())
            self.model.appendRow(items)
            count += 1
        self.status.setText('显示前 512 个参数。' if pending else f'{count} 个参数 · 只读模板')

    def dispose(self):
        # No global scene callback or polling timer is installed by this example.
        self.set_node(None)


def create_panel():
    return NodeReferencePanel()
