#pragma once

#include <QMainWindow>
#include <QAction>
#include <QActionGroup>
#include <QMenu>
#include <QDockWidget>
#include <QStackedWidget>
#include <QHash>
#include <QVector>

#include "ProjectModel.h"

class ProjectDock;
class LayerDock;
class PropertiesDock;
class TaskDock;
class LogDock;
class WelcomeWorkspace;
class ProjectWorkspace;
class RasterViewerWidget;

class MainWindow : public QMainWindow {
    Q_OBJECT
public:
    explicit MainWindow(QWidget* parent = nullptr);
    ~MainWindow() override = default;

private slots:
    void newProject();
    void openProject();
    void saveProject();
    void saveProjectAs();
    void importResource();
    void showAbout();
    void changeLanguage(const QString& language);
    void changeTheme(const QString& themeName);
    void switchPanel(const QString& name);

private:
    void createActions();
    void createMenuBar();
    void createDocks();
    void createCentralWidget();
    void createStatusBar();
    void retranslateUi();
    void retranslateActions();
    void retranslateMenuBar();
    void retranslateDocks();
    void refreshProjectViews();
    void updateWindowTitle();
    void applyTheme(const QString& name);
    void showStatusMessage(const QString& message, int timeoutMs = 5000);

    QWidget* ensureTab(const QString& name);

    QDockWidget* addDockWidgetHelper(const QString& key, QWidget* widget,
                                      Qt::DockWidgetArea area);

    void connectViewerCursors(QWidget* widget);
    void disconnectViewerCursors();
    void onViewerCursorUpdate(int px, int py, double geoX, double geoY);

    // Project
    ProjectModel m_project;

    // Central workspace
    QStackedWidget* m_workspaceStack;
    WelcomeWorkspace* m_welcomeWorkspace;
    ProjectWorkspace* m_projectWorkspace;

    // Tab state
    QVector<QString> m_tabNames;
    QHash<QString, int> m_tabIndices;
    QHash<QString, QWidget*> m_tabs;
    QHash<QString, QAction*> m_tabActions;
    QVector<QMetaObject::Connection> m_cursorConnections;

    // Docks
    ProjectDock* m_projectDock;
    LayerDock* m_layerDock;
    PropertiesDock* m_propertiesDock;
    TaskDock* m_taskDock;
    LogDock* m_logDock;
    QHash<QString, QDockWidget*> m_docks;

    // Actions
    QAction* m_actionNew;
    QAction* m_actionOpen;
    QAction* m_actionSave;
    QAction* m_actionSaveAs;
    QAction* m_actionImportResource;
    QAction* m_actionExit;
    QAction* m_actionAbout;

    QActionGroup* m_languageGroup;
    QAction* m_actionLangZh;
    QAction* m_actionLangEn;

    QActionGroup* m_themeGroup;
    QAction* m_actionThemeLight;
    QAction* m_actionThemeDark;

    // Menus
    QMenu* m_fileMenu;
    QMenu* m_functionsMenu;
    QMenu* m_viewMenu;
    QMenu* m_themeMenu;
    QMenu* m_toolsMenu;
    QMenu* m_languageMenu;
    QMenu* m_helpMenu;

    // Theme
    QString m_currentTheme;
};
