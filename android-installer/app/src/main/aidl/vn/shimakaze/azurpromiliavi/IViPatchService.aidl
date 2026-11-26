package vn.shimakaze.azurpromiliavi;

interface IViPatchService {
    void destroy() = 16777114;
    String detectResVersion(String gameFilesDir) = 1;
    String probeGameState(String gameFilesDir, String manifestJson) = 2;
    String forceStopGame(String packageName) = 3;
    String installFromStaging(String stagingDir, String gameFilesDir, String manifestJson) = 4;
    String restoreFromBackup(String gameFilesDir, String manifestJson) = 5;
}
