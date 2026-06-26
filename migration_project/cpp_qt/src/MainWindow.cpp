#include "MainWindow.h"
#include "I18n.h"
#include "ThemeManager.h"

#include "docks/ProjectDock.h"
#include "docks/LayerDock.h"
#include "docks/PropertiesDock.h"
#include "docks/TaskDock.h"
#include "docks/LogDock.h"
#include "workspaces/WelcomeWorkspace.h"
#include "workspaces/ProjectWorkspace.h"
#include "widgets/RasterViewerWidget.h"
#include "tabs/ImageProcessingTab.h"

#include <QApplication>
#include <QMenuBar>
#include <QStatusBar>
#include <QFileDialog>
#include <QInputDialog>
#include <QMessageBox>
#include <QFileInfo>
#include <QShortcut>
#include <QLabel>
#include <QVBoxLayout>
#include <QDebug>

static const char* kAppVersion = "0.3.0";

MainWindow::MainWindow(QWidget* parent)
    : QMainWindow(parent)
    , m_currentTheme(ThemeManager::DEFAULT_THEME)
{
    m_tabNames = {
        "feature", "image_processing", "match",
        "detection", "vector", "viewer_3d"
    };

    setMinimumSize(1120, 720);
    resize(1440, 900);

    applyTheme(m_currentTheme);
    createCentralWidget();
    createActions();
    createMenuBar();
    createDocks();
    createStatusBar();

    refreshProjectViews();
    m_logDock->append(I18n::instance().tr("log.initialized"));
}

// --- Central Widget ---

void MainWindow::createCentralWidget() {
    m_workspaceStack = new QStackedWidget(this);
    m_welcomeWorkspace = new WelcomeWorkspace(this);
    m_projectWorkspace = new ProjectWorkspace(this);
    m_workspaceStack->addWidget(m_welcomeWorkspace);   // index 0
    m_workspaceStack->addWidget(m_projectWorkspace);    // index 1
    m_tabIndices["welcome"] = 0;
    m_tabIndices["project"] = 1;

    // Add placeholder tabs
    for (const QString& name : m_tabNames) {
        auto* placeholder = new QLabel(
            I18n::instance().tr("tab." + name), this);
        placeholder->setAlignment(Qt::AlignCenter);
        placeholder->setStyleSheet("color: #666; font-size: 18px;");
        int idx = m_workspaceStack->addWidget(placeholder);
        m_tabIndices[name] = idx;
    }

    setCentralWidget(m_workspaceStack);
}

// --- Actions ---

void MainWindow::createActions() {
    m_actionNew = new QAction(this);
    m_actionNew->setShortcut(QKeySequence::New);
    connect(m_actionNew, &QAction::triggered, this, &MainWindow::newProject);

    m_actionOpen = new QAction(this);
    m_actionOpen->setShortcut(QKeySequence::Open);
    connect(m_actionOpen, &QAction::triggered, this, &MainWindow::openProject);

    m_actionSave = new QAction(this);
    m_actionSave->setShortcut(QKeySequence::Save);
    connect(m_actionSave, &QAction::triggered, this, &MainWindow::saveProject);

    m_actionSaveAs = new QAction(this);
    m_actionSaveAs->setShortcut(QKeySequence::SaveAs);
    connect(m_actionSaveAs, &QAction::triggered, this, &MainWindow::saveProjectAs);

    m_actionImportResource = new QAction(this);
    m_actionImportResource->setShortcut(QKeySequence("Ctrl+I"));
    connect(m_actionImportResource, &QAction::triggered, this, &MainWindow::importResource);

    m_actionExit = new QAction(this);
    m_actionExit->setShortcut(QKeySequence::Quit);
    connect(m_actionExit, &QAction::triggered, this, &QWidget::close);

    m_actionAbout = new QAction(this);
    connect(m_actionAbout, &QAction::triggered, this, &MainWindow::showAbout);

    // Language group
    m_languageGroup = new QActionGroup(this);
    m_languageGroup->setExclusive(true);

    m_actionLangZh = new QAction(this);
    m_actionLangZh->setCheckable(true);
    connect(m_actionLangZh, &QAction::triggered, this, [this]() { changeLanguage("zh"); });
    m_languageGroup->addAction(m_actionLangZh);

    m_actionLangEn = new QAction(this);
    m_actionLangEn->setCheckable(true);
    connect(m_actionLangEn, &QAction::triggered, this, [this]() { changeLanguage("en"); });
    m_languageGroup->addAction(m_actionLangEn);

    // Theme group
    m_themeGroup = new QActionGroup(this);
    m_themeGroup->setExclusive(true);

    m_actionThemeLight = new QAction(this);
    m_actionThemeLight->setCheckable(true);
    connect(m_actionThemeLight, &QAction::triggered, this, [this]() { changeTheme("light"); });
    m_themeGroup->addAction(m_actionThemeLight);

    m_actionThemeDark = new QAction(this);
    m_actionThemeDark->setCheckable(true);
    connect(m_actionThemeDark, &QAction::triggered, this, [this]() { changeTheme("dark"); });
    m_themeGroup->addAction(m_actionThemeDark);

    retranslateActions();
}

// --- Menu Bar ---

void MainWindow::createMenuBar() {
    menuBar()->clear();

    m_fileMenu = menuBar()->addMenu("");
    m_fileMenu->addAction(m_actionNew);
    m_fileMenu->addAction(m_actionOpen);
    m_fileMenu->addSeparator();
    m_fileMenu->addAction(m_actionSave);
    m_fileMenu->addAction(m_actionSaveAs);
    m_fileMenu->addSeparator();
    m_fileMenu->addAction(m_actionImportResource);
    m_fileMenu->addSeparator();
    m_fileMenu->addAction(m_actionExit);

    m_functionsMenu = menuBar()->addMenu("");
    m_tabActions.clear();
    for (const QString& name : m_tabNames) {
        QAction* action = new QAction(I18n::instance().tr("tab." + name), this);
        connect(action, &QAction::triggered, this, [this, name]() {
            switchPanel(name);
        });
        m_functionsMenu->addAction(action);
        m_tabActions[name] = action;
    }

    m_viewMenu = menuBar()->addMenu("");
    m_themeMenu = m_viewMenu->addMenu("");
    m_themeMenu->addAction(m_actionThemeLight);
    m_themeMenu->addAction(m_actionThemeDark);
    m_viewMenu->addSeparator();

    m_toolsMenu = menuBar()->addMenu("");
    m_toolsMenu->addAction(m_actionImportResource);

    m_languageMenu = menuBar()->addMenu("");
    m_languageMenu->addAction(m_actionLangZh);
    m_languageMenu->addAction(m_actionLangEn);

    m_helpMenu = menuBar()->addMenu("");
    m_helpMenu->addAction(m_actionAbout);

    retranslateMenuBar();
}

// --- Docks ---

QDockWidget* MainWindow::addDockWidgetHelper(const QString& key, QWidget* widget,
                                               Qt::DockWidgetArea area) {
    auto* dock = new QDockWidget(this);
    dock->setObjectName(key);
    dock->setWidget(widget);
    dock->setAllowedAreas(Qt::LeftDockWidgetArea | Qt::RightDockWidgetArea | Qt::BottomDockWidgetArea);
    addDockWidget(area, dock);
    m_viewMenu->addAction(dock->toggleViewAction());
    m_docks[key] = dock;
    return dock;
}

void MainWindow::createDocks() {
    m_projectDock = new ProjectDock(this);
    m_layerDock = new LayerDock(this);
    m_propertiesDock = new PropertiesDock(this);
    m_taskDock = new TaskDock(this);
    m_logDock = new LogDock(this);

    addDockWidgetHelper("dock.project", m_projectDock, Qt::LeftDockWidgetArea);
    addDockWidgetHelper("dock.layers", m_layerDock, Qt::LeftDockWidgetArea);
    addDockWidgetHelper("dock.properties", m_propertiesDock, Qt::RightDockWidgetArea);
    addDockWidgetHelper("dock.tasks", m_taskDock, Qt::BottomDockWidgetArea);
    addDockWidgetHelper("dock.log", m_logDock, Qt::BottomDockWidgetArea);

    tabifyDockWidget(m_docks["dock.tasks"], m_docks["dock.log"]);

    retranslateDocks();
}

// --- Status Bar ---

void MainWindow::createStatusBar() {
    statusBar()->showMessage(I18n::instance().tr("status.ready"));
}

// --- Slots ---

void MainWindow::newProject() {
    bool ok = false;
    QString name = QInputDialog::getText(this,
        I18n::instance().tr("dialog.new_project.title"),
        I18n::instance().tr("dialog.new_project.name"),
        QLineEdit::Normal, "", &ok);
    if (!ok || name.trimmed().isEmpty())
        return;

    QString path = QFileDialog::getSaveFileName(this,
        I18n::instance().tr("dialog.save_project.title"),
        name.trimmed() + ".rstao",
        I18n::instance().tr("filter.project"));
    if (path.isEmpty())
        return;

    if (m_project.newProject(name.trimmed(), path)) {
        refreshProjectViews();
        showStatusMessage(I18n::instance().tr("status.project_created"));
        m_logDock->append(I18n::instance().tr("log.project_created", {{"path", path}}));
    } else {
        QMessageBox::warning(this,
            I18n::instance().tr("dialog.new_project.title"),
            I18n::instance().tr("dialog.warning.create_failed"));
    }
}

void MainWindow::openProject() {
    QString path = QFileDialog::getOpenFileName(this,
        I18n::instance().tr("dialog.open_project.title"),
        "",
        I18n::instance().tr("filter.project_all"));
    if (path.isEmpty())
        return;

    if (!m_project.loadProject(path)) {
        QMessageBox::warning(this,
            I18n::instance().tr("dialog.open_project.title"),
            I18n::instance().tr("dialog.warning.open_failed"));
        return;
    }

    refreshProjectViews();
    showStatusMessage(I18n::instance().tr("status.project_opened"));
    m_logDock->append(I18n::instance().tr("log.project_opened", {{"path", path}}));
}

void MainWindow::saveProject() {
    if (!m_project.isOpen()) {
        saveProjectAs();
        return;
    }
    if (m_project.saveProject()) {
        refreshProjectViews();
        showStatusMessage(I18n::instance().tr("status.project_saved"));
        m_logDock->append(I18n::instance().tr("log.project_saved"));
    } else {
        QMessageBox::warning(this,
            I18n::instance().tr("dialog.save_project.title"),
            I18n::instance().tr("dialog.warning.save_failed"));
    }
}

void MainWindow::saveProjectAs() {
    if (!m_project.isOpen()) {
        QMessageBox::information(this,
            I18n::instance().tr("dialog.save_project.title"),
            I18n::instance().tr("dialog.warning.need_project"));
        return;
    }

    QString currentName = m_project.projectName();
    if (currentName.isEmpty())
        currentName = I18n::instance().tr("project.untitled");

    QString path = QFileDialog::getSaveFileName(this,
        I18n::instance().tr("dialog.save_project_as.title"),
        currentName + ".rstao",
        I18n::instance().tr("filter.project"));
    if (path.isEmpty())
        return;

    if (m_project.saveProjectAs(path)) {
        refreshProjectViews();
        showStatusMessage(I18n::instance().tr("status.project_saved_as"));
        m_logDock->append(I18n::instance().tr("log.project_saved_as", {{"path", path}}));
    } else {
        QMessageBox::warning(this,
            I18n::instance().tr("dialog.save_project_as.title"),
            I18n::instance().tr("dialog.warning.save_failed"));
    }
}

void MainWindow::importResource() {
    if (!m_project.isOpen()) {
        QMessageBox::information(this,
            I18n::instance().tr("dialog.import_resource.title"),
            I18n::instance().tr("dialog.warning.need_project"));
        return;
    }

    QString path = QFileDialog::getOpenFileName(this,
        I18n::instance().tr("dialog.import_resource.title"),
        "",
        I18n::instance().tr("filter.resources"));
    if (path.isEmpty())
        return;

    QJsonObject record;
    record["name"] = QFileInfo(path).fileName();
    record["source_path"] = path;

    m_project.addResource(record);
    m_project.saveProject();

    refreshProjectViews();
    showStatusMessage(I18n::instance().tr("status.resource_imported"));
    m_logDock->append(I18n::instance().tr("log.resource_imported", {{"path", path}}));
}

void MainWindow::showAbout() {
    QMessageBox::about(this,
        I18n::instance().tr("dialog.about.title"),
        I18n::instance().tr("dialog.about.body", {{"version", kAppVersion}}));
}

void MainWindow::changeLanguage(const QString& language) {
    if (!I18n::instance().setLanguage(language))
        return;
    retranslateUi();
    m_logDock->append(I18n::instance().tr(
        QString("log.language_changed.%1").arg(I18n::instance().currentLanguage())));
}

void MainWindow::changeTheme(const QString& themeName) {
    if (!ThemeManager::instance().setTheme(themeName))
        return;
    m_currentTheme = themeName;
    retranslateActions();  // update check states
    showStatusMessage(I18n::instance().tr(
        QString("status.theme_changed.%1").arg(themeName)));
}

// --- Cursor coordinate wiring ------------------------------------------------

void MainWindow::connectViewerCursors(QWidget* widget) {
    auto viewers = widget->findChildren<RasterViewerWidget*>();
    for (auto* viewer : viewers) {
        auto conn = connect(viewer, &RasterViewerWidget::cursorMoved,
                           this, &MainWindow::onViewerCursorUpdate);
        m_cursorConnections.append(conn);
    }
}

void MainWindow::disconnectViewerCursors() {
    for (auto& conn : m_cursorConnections) {
        QObject::disconnect(conn);
    }
    m_cursorConnections.clear();
}

void MainWindow::onViewerCursorUpdate(int px, int py, double geoX, double geoY) {
    QVariantHash args;
    args["px"] = px;
    args["py"] = py;
    args["geo_x"] = QString::number(geoX, 'f', 6);
    args["geo_y"] = QString::number(geoY, 'f', 6);
    statusBar()->showMessage(
        I18n::instance().tr("raster.cursor_coords", args));
}

// --- Tab management ----------------------------------------------------------

QWidget* MainWindow::ensureTab(const QString& name) {
    if (m_tabs.contains(name))
        return m_tabs[name];

    int idx = m_tabIndices.value(name, -1);
    if (idx < 0 || idx >= m_workspaceStack->count())
        return nullptr;

    QWidget* tab = nullptr;

    if (name == "image_processing") {
        tab = new ImageProcessingTab(nullptr);
    } else {
        auto* lbl = new QLabel(I18n::instance().tr("tab." + name), nullptr);
        lbl->setStyleSheet("color: #666; font-size: 18px;");
        lbl->setAlignment(Qt::AlignCenter);
        tab = lbl;
    }

    if (tab) {
        QWidget* old = m_workspaceStack->widget(idx);
        m_workspaceStack->addWidget(tab);   // keep placeholder, add new at end
        m_tabs[name] = tab;
    }
    return tab;
}

void MainWindow::switchPanel(const QString& name) {
    disconnectViewerCursors();

    QWidget* widget = nullptr;

    if (m_tabNames.contains(name)) {
        widget = ensureTab(name);
    } else if (name == "project") {
        widget = m_projectWorkspace;
    }

    if (widget) {
        m_workspaceStack->setCurrentWidget(widget);
        connectViewerCursors(widget);
    }
}

// --- Theme ---

void MainWindow::applyTheme(const QString& name) {
    auto* app = qobject_cast<QApplication*>(QApplication::instance());
    if (app)
        app->setStyleSheet(ThemeManager::instance().loadStyleSheet(name));
}

// --- Retranslation ---

void MainWindow::retranslateUi() {
    retranslateActions();
    retranslateMenuBar();
    retranslateDocks();
    m_welcomeWorkspace->retranslateUi();
    m_projectWorkspace->retranslateUi();
    m_projectDock->retranslateUi();
    m_layerDock->retranslateUi();
    m_propertiesDock->retranslateUi();
    m_taskDock->retranslateUi();
    updateWindowTitle();
    statusBar()->showMessage(I18n::instance().tr("status.ready"));

    // Propagate to loaded tabs
    for (auto* tab : m_tabs) {
        // tabs will implement retranslateUi() via a common interface
        QMetaObject::invokeMethod(tab, "retranslateUi", Qt::DirectConnection);
    }
}

void MainWindow::retranslateActions() {
    m_actionNew->setText(I18n::instance().tr("action.new_project"));
    m_actionOpen->setText(I18n::instance().tr("action.open_project"));
    m_actionSave->setText(I18n::instance().tr("action.save_project"));
    m_actionSaveAs->setText(I18n::instance().tr("action.save_project_as"));
    m_actionImportResource->setText(I18n::instance().tr("action.import_resource"));
    m_actionExit->setText(I18n::instance().tr("action.exit"));
    m_actionAbout->setText(I18n::instance().tr("action.about"));
    m_actionLangZh->setText(I18n::instance().tr("language.zh"));
    m_actionLangEn->setText(I18n::instance().tr("language.en"));
    m_actionLangZh->setChecked(I18n::instance().currentLanguage() == "zh");
    m_actionLangEn->setChecked(I18n::instance().currentLanguage() == "en");
    m_actionThemeLight->setText(I18n::instance().tr("theme.light"));
    m_actionThemeDark->setText(I18n::instance().tr("theme.dark"));
    m_actionThemeLight->setChecked(m_currentTheme == "light");
    m_actionThemeDark->setChecked(m_currentTheme == "dark");
}

void MainWindow::retranslateMenuBar() {
    m_fileMenu->setTitle(I18n::instance().tr("menu.file"));
    m_functionsMenu->setTitle(I18n::instance().tr("menu.functions"));
    m_viewMenu->setTitle(I18n::instance().tr("menu.view"));
    m_themeMenu->setTitle(I18n::instance().tr("menu.theme"));
    m_toolsMenu->setTitle(I18n::instance().tr("menu.tools"));
    m_languageMenu->setTitle(I18n::instance().tr("menu.language"));
    m_helpMenu->setTitle(I18n::instance().tr("menu.help"));

    // Tab actions
    for (auto it = m_tabActions.cbegin(); it != m_tabActions.cend(); ++it) {
        it.value()->setText(I18n::instance().tr("tab." + it.key()));
    }
}

void MainWindow::retranslateDocks() {
    for (auto it = m_docks.cbegin(); it != m_docks.cend(); ++it) {
        it.value()->setWindowTitle(I18n::instance().tr(it.key()));
    }
}

// --- View Helpers ---

void MainWindow::refreshProjectViews() {
    QJsonObject proj = m_project.toJson();
    QString path = m_project.projectPath();

    m_projectDock->setProject(proj, path);
    m_layerDock->setProject(proj);
    m_propertiesDock->showProject(proj, path);
    m_projectWorkspace->showProject(proj, path);

    if (m_project.isOpen()) {
        m_workspaceStack->setCurrentWidget(m_projectWorkspace);
    } else {
        m_workspaceStack->setCurrentWidget(m_welcomeWorkspace);
    }

    updateWindowTitle();
}

void MainWindow::updateWindowTitle() {
    QString appTitle = I18n::instance().tr("app.title");
    if (m_project.isOpen()) {
        QString name = m_project.projectName();
        if (name.isEmpty())
            name = I18n::instance().tr("project.untitled");
        setWindowTitle(QString("%1 - %2 %3").arg(name, appTitle, kAppVersion));
    } else {
        setWindowTitle(QString("%1 %2").arg(appTitle, kAppVersion));
    }
}

void MainWindow::showStatusMessage(const QString& message, int timeoutMs) {
    statusBar()->showMessage(message, timeoutMs);
}
