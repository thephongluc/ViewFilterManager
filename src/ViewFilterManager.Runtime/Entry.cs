using System.IO;
using System.ComponentModel;
using System.Reflection;
using System.Runtime.Loader;
using System.Windows;
using System.Windows.Interop;
using IronPython.Hosting;
using Microsoft.Scripting.Hosting;

namespace ViewFilterManager.Runtime;

public class ReactiveObject : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;
    public void OnPropertyChanged(string property) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(property));
}

public static class Context
{
    public static dynamic? Application { get; internal set; }
    public static void SetOwner(Window window)
    {
        if (Application is not null) new WindowInteropHelper(window).Owner = (IntPtr)Application.MainWindowHandle;
        window.ShowInTaskbar = false;
    }
}

public static class Entry
{
    private static ScriptEngine? engine;
    public static void Run(object application, string content)
    {
        Context.Application = application;
        try
        {
            engine ??= CreateEngine(content);
            foreach (var name in new[] { "RevitAPI", "RevitAPIUI" })
                engine.Runtime.LoadAssembly(AppDomain.CurrentDomain.GetAssemblies().First(a => a.GetName().Name == name));
            var scope = engine.CreateScope();
            scope.SetVariable("bundle", content);
            engine.Execute("from tpt_vfm.ui import ManagerWindow\nManagerWindow(bundle).ShowDialog()", scope);
        }
        catch (Exception ex)
        {
            var details = engine?.GetService<ExceptionOperations>().FormatException(ex) ?? ex.ToString();
            throw new InvalidOperationException(details, ex);
        }
        finally { Context.Application = null; }
    }

    // Also used by the offline harness; no Revit process or pyRevit is required.
    public static ScriptEngine CreateEngine(string content)
    {
        var result = Python.CreateEngine(new Dictionary<string, object> { ["Frames"] = true, ["FullFrames"] = true });
        var folder = Path.GetDirectoryName(typeof(Entry).Assembly.Location)!;
        result.SetSearchPaths(new[] { content, Path.Combine(folder, "Lib") });
        foreach (var assembly in new[] { typeof(Entry).Assembly, typeof(Window).Assembly,
            typeof(System.Windows.Media.Brush).Assembly, typeof(System.Windows.Threading.Dispatcher).Assembly })
            result.Runtime.LoadAssembly(assembly);
        foreach (var file in new[] { "IronPython.Modules.dll", "IronPython.Wpf.dll" })
            result.Runtime.LoadAssembly(AssemblyLoadContext.GetLoadContext(typeof(Entry).Assembly)!.LoadFromAssemblyPath(Path.Combine(folder, file)));
        result.Execute("import sys\nsys.dont_write_bytecode = True");
        return result;
    }
}
