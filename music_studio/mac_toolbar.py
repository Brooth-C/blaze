"""Standard AppKit toolbar and commands for the retained web detail view."""


def toolbar_identifiers():
    import AppKit
    return ['blaze.sidebar', AppKit.NSToolbarFlexibleSpaceItemIdentifier,
            'blaze.search', 'blaze.import', 'blaze.player', 'blaze.settings']


def build_toolbar(owner):
    import AppKit
    toolbar = AppKit.NSToolbar.alloc().initWithIdentifier_('BlazeMainToolbar')
    toolbar.setDisplayMode_(AppKit.NSToolbarDisplayModeIconOnly)
    toolbar.setAllowsUserCustomization_(False)
    toolbar.setAutosavesConfiguration_(False)
    for identifier, label, symbol, action in (
        ('blaze.sidebar', 'Show or Hide Sidebar', 'sidebar.left', 'toggleSidebar:'),
        ('blaze.import', 'Import File', 'square.and.arrow.down', 'importFile:'),
        ('blaze.player', 'Now Playing', 'play.rectangle', 'openPlayer:'),
        ('blaze.settings', 'Settings', 'gearshape', 'openSettings:'),
    ):
        item = AppKit.NSToolbarItem.alloc().initWithItemIdentifier_(identifier)
        item.setLabel_(label)
        item.setPaletteLabel_(label)
        item.setToolTip_(label)
        item.setImage_(AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol, label))
        item.setTarget_(owner.target)
        item.setAction_(action)
        owner.toolbar_items[identifier] = item
    search = AppKit.NSSearchToolbarItem.alloc().initWithItemIdentifier_('blaze.search')
    search.setLabel_('Search')
    search.setToolTip_('Search songs, videos and artists (⌘F)')
    search.setPreferredWidthForSearchField_(300)
    field = search.searchField()
    field.setPlaceholderString_('Search songs, videos, artists')
    field.setAccessibilityLabel_('Search Blaze')
    field.setSendsWholeSearchString_(True)
    field.setSendsSearchStringImmediately_(False)
    field.setDelegate_(owner.target)
    field.setTarget_(owner.target)
    field.setAction_('searchCommit:')
    owner.search_item = search
    owner.toolbar_items['blaze.search'] = search
    toolbar.setDelegate_(owner.target)
    owner.native.setToolbar_(toolbar)


def install_menus(owner):
    """Preserve Cocoa's existing app/Edit menus and responder chain."""
    import AppKit
    main = AppKit.NSApp.mainMenu()
    if main is None:
        return

    def add(menu, title, action, key='', tag=0, index=None):
        item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
        item.setTarget_(owner.target)
        item.setTag_(tag)
        if key:
            item.setKeyEquivalentModifierMask_(AppKit.NSEventModifierFlagCommand)
        if index is None:
            menu.addItem_(item)
        else:
            menu.insertItem_atIndex_(item, index)
        owner.menu_items.append((menu, item))
        return item

    app_menu = main.itemAtIndex_(0).submenu() if main.numberOfItems() else None
    if app_menu is not None:
        add(app_menu, 'Settings…', 'openSettings:', ',', index=min(2, app_menu.numberOfItems()))
    file_root = next((item for item in main.itemArray() if item.title() == 'File'), None)
    if file_root is None:
        file_root = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('File', None, '')
        file_menu = AppKit.NSMenu.alloc().initWithTitle_('File')
        file_root.setSubmenu_(file_menu)
        main.insertItem_atIndex_(file_root, min(1, main.numberOfItems()))
        owner.menu_items.append((main, file_root))
    else:
        file_menu = file_root.submenu()
    add(file_menu, 'Open in Studio…', 'importFile:', 'o')
    view_root = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Navigate', None, '')
    view_menu = AppKit.NSMenu.alloc().initWithTitle_('Navigate')
    view_root.setSubmenu_(view_menu)
    # Keep navigation alongside Edit/View, before Window and Help if present.
    position = next((i for i, item in enumerate(main.itemArray())
                     if item.title() in ('Window', 'Help')), main.numberOfItems())
    main.insertItem_atIndex_(view_root, position)
    owner.menu_items.append((main, view_root))
    add(view_menu, 'Search', 'focusSearch:', 'f')
    for title, tag, key in [('Explore', 0, '1'), ('Library', 2, '2'),
                            ('Downloads', 1, '3'), ('Music Studio', 3, '4')]:
        add(view_menu, title, 'selectSection:', key, tag)
    add(view_menu, 'Show or Hide Sidebar', 'toggleSidebar:')
    add(view_menu, 'Now Playing', 'openPlayer:')
    add(view_menu, 'Play or Pause', 'playback:', tag=0)
    add(view_menu, 'Back 10 Seconds', 'playback:', tag=1)
    add(view_menu, 'Next', 'playback:', tag=2)
