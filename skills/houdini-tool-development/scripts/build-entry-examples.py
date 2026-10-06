"""Stage editable Panel/Viewer State/Shelf resources without installing them.

The source assets are the single maintenance source. Use tool_package_create
to register the chosen editable resource directory; this script emits no launcher
or environment changes and refuses to overwrite an existing resource tree.
"""
import argparse
from pathlib import Path
import shutil
from xml.etree import ElementTree as ET


def build(output, python_version):
    output = Path(output).resolve()
    if python_version not in ('3.11', '3.13'):
        raise ValueError('examples target the declared H21/H22 Python versions 3.11 or 3.13')
    if output.exists() and any(output.iterdir()):
        raise ValueError('choose an empty resource directory; existing files are not replaced')
    output.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[1] / 'assets/tool-entry-examples'
    modules = output / f'python{python_version}libs'
    panels, states, toolbar = (output / name for name in ('python_panels', 'viewer_states', 'toolbar'))
    for directory in (modules, panels, states, toolbar):
        directory.mkdir()
    for name in ('dsh_artist_example_panel.py', 'dsh_artist_example_state.py'):
        shutil.copy2(source / name, modules / name)
    (states / 'dsh_artist_example.py').write_text(
        'from dsh_artist_example_state import createViewerStateTemplate\n', encoding='utf-8')
    document = ET.Element('pythonPanelDocument')
    interface = ET.SubElement(document, 'interface', name='dsh_artist_example_reference',
        label='Reference Node', icon='SOP_null', help_url='', showNetworkNavigationBar='false')
    ET.SubElement(interface, 'script').text = '''from dsh_artist_example_panel import create_panel
panel = None
def onCreateInterface():
    global panel
    panel = create_panel()
    return panel
def onDestroyInterface():
    global panel
    if panel is not None:
        panel.dispose()
    panel = None
def onNodePathChanged(node):
    if panel is not None:
        panel.set_node(node)
def onHipFileBeforeClear():
    if panel is not None:
        panel.set_node(None)
def onHipFileBeforeLoad():
    onHipFileBeforeClear()
'''
    ET.SubElement(interface, 'includeInPaneTabMenu', menu_position='100', create_separator='false')
    ET.SubElement(interface, 'includeInToolbarMenu', menu_position='100', create_separator='false')
    # Match the native editor export, including complete interface metadata and
    # a CDATA script, rather than assuming generic XML output loads identically.
    script = interface.find('script')
    script_text = script.text
    script.text = 'DSH_ARTIST_SCRIPT_CDATA'
    ET.indent(document, space='  ')
    panel_xml = ET.tostring(document, encoding='unicode').replace(
        'DSH_ARTIST_SCRIPT_CDATA', '<![CDATA[' + script_text + ']]>')
    (panels / 'dsh_artist_example.pypanel').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n' + panel_xml, encoding='utf-8')
    shelf = ET.Element('shelfDocument')
    tool = ET.SubElement(shelf, 'tool', name='dsh_artist_example_plane_inspect',
        label='Inspect XZ Plane', icon='SOP_null')
    ET.SubElement(tool, 'script', scriptType='python').text = (
        'from dsh_artist_example_state import enter_from_shelf\nenter_from_shelf(kwargs)\n')
    # Shelf scripts use the same vendor-native CDATA representation.
    shelf_script = tool.find('script')
    shelf_text = shelf_script.text
    shelf_script.text = 'DSH_ARTIST_SHELF_CDATA'
    ET.indent(shelf, space='  ')
    shelf_xml = ET.tostring(shelf, encoding='unicode').replace(
        'DSH_ARTIST_SHELF_CDATA', '<![CDATA[' + shelf_text + ']]>')
    (toolbar / 'dsh_artist_example.shelf').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n' + shelf_xml, encoding='utf-8')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--python-version', required=True, choices=('3.11', '3.13'))
    args = parser.parse_args()
    print(build(args.output, args.python_version))
