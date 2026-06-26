#include <QApplication>
#include "MainWindow.h"
#include "I18n.h"
#include "ThemeManager.h"

int main(int argc, char* argv[]) {
    QApplication app(argc, argv);
    app.setApplicationName("RSTao Studio");
    app.setOrganizationName("RSTao");
    app.setApplicationVersion("0.1.0");

    // Default theme
    app.setStyleSheet(ThemeManager::instance().loadStyleSheet(ThemeManager::DEFAULT_THEME));

    MainWindow window;
    window.show();

    return app.exec();
}
