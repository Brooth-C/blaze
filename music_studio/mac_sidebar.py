"""System source-list views for the Mac window, without product state."""

ROWS = (
    ('group-browse', 'Browse', None),
    ('explore', 'Explore', 'sparkles'),
    ('group-music', 'Your Music', None),
    ('library', 'Library', 'music.note.list'),
    ('downloads', 'Downloads', 'arrow.down.circle'),
    ('group-create', 'Create', None),
    ('studio', 'Music Studio', 'waveform'),
)


def row_for_section(section):
    return next((index for index, row in enumerate(ROWS) if row[0] == section and row[2]), -1)


def row_view(outline, key):
    import AppKit
    row = next((row for row in ROWS if row[0] == key), None)
    if row is None:
        return None
    group = row[2] is None
    identifier = 'BlazeSidebarGroup' if group else 'BlazeSidebarItem'
    cell = outline.makeViewWithIdentifier_owner_(identifier, None)
    if cell is None:
        cell = AppKit.NSTableCellView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 200, 32))
        cell.setIdentifier_(identifier)
        label = AppKit.NSTextField.labelWithString_('')
        label.setFrame_(AppKit.NSMakeRect(8 if group else 32, 7, 152 if group else 128, 18))
        label.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        label.setFont_(AppKit.NSFont.systemFontOfSize_weight_(11 if group else 13,
            AppKit.NSFontWeightSemibold if group else AppKit.NSFontWeightRegular))
        label.setTextColor_(AppKit.NSColor.secondaryLabelColor() if group else AppKit.NSColor.labelColor())
        label.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
        cell.addSubview_(label)
        cell.setTextField_(label)
        if not group:
            icon = AppKit.NSImageView.alloc().initWithFrame_(AppKit.NSMakeRect(8, 8, 16, 16))
            icon.setContentTintColor_(AppKit.NSColor.secondaryLabelColor())
            cell.addSubview_(icon)
            cell.setImageView_(icon)
    cell.textField().setStringValue_(row[1])
    cell.setAccessibilityLabel_(row[1])
    if not group:
        cell.imageView().setImage_(AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(row[2], row[1]))
    return cell


def build_sidebar(target, glass):
    import AppKit
    frame = AppKit.NSMakeRect(0, 0, 210, 700)
    content = AppKit.NSView.alloc().initWithFrame_(frame)
    content.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
    scroll = AppKit.NSScrollView.alloc().initWithFrame_(AppKit.NSMakeRect(8, 0, 194, 690))
    scroll.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
    scroll.setDrawsBackground_(False)
    scroll.setHasVerticalScroller_(True)
    scroll.setAutohidesScrollers_(True)
    outline = AppKit.NSOutlineView.alloc().initWithFrame_(scroll.bounds())
    column = AppKit.NSTableColumn.alloc().initWithIdentifier_('BlazeNavigation')
    column.setWidth_(194)
    outline.addTableColumn_(column)
    outline.setOutlineTableColumn_(column)
    outline.setHeaderView_(None)
    outline.setStyle_(AppKit.NSTableViewStyleSourceList)
    outline.setBackgroundColor_(AppKit.NSColor.clearColor())
    outline.setRowHeight_(32)
    outline.setIndentationPerLevel_(0)
    outline.setIntercellSpacing_(AppKit.NSMakeSize(0, 2))
    outline.setAllowsEmptySelection_(False)
    outline.setAllowsMultipleSelection_(False)
    outline.setColumnAutoresizingStyle_(AppKit.NSTableViewLastColumnOnlyAutoresizingStyle)
    outline.setAccessibilityLabel_('Blaze navigation')
    outline.setDataSource_(target)
    outline.setDelegate_(target)
    scroll.setDocumentView_(outline)
    content.addSubview_(scroll)
    if glass is not None:
        surface = glass.alloc().initWithFrame_(frame)
        surface.setContentView_(content)
        surface.setStyle_(AppKit.NSGlassEffectViewStyleRegular)
        material = 'liquid-glass'
    else:
        surface = AppKit.NSVisualEffectView.alloc().initWithFrame_(frame)
        surface.setMaterial_(AppKit.NSVisualEffectMaterialSidebar)
        surface.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        surface.setState_(AppKit.NSVisualEffectStateFollowsWindowActiveState)
        surface.addSubview_(content)
        material = 'system-vibrancy'
    surface.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
    controller = AppKit.NSViewController.alloc().init()
    controller.setView_(surface)
    outline.reloadData()
    return controller, outline, surface, material
