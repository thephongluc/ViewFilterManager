using System.IO;
using System.Reflection;
using System.Runtime.Loader;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using System.Windows.Media.Imaging;

namespace ViewFilterManager.Addin;

public sealed class Application : IExternalApplication
{
    public Result OnStartup(UIControlledApplication app)
    {
        if (app.ControlledApplication.VersionNumber != "2026") return Result.Failed;
        const string tab = "View Filter Manager";
        try { app.CreateRibbonTab(tab); } catch (Autodesk.Revit.Exceptions.ArgumentException) { }
        var panel = app.GetRibbonPanels(tab).FirstOrDefault(p => p.Name == "View Filter Manager")
                    ?? app.CreateRibbonPanel(tab, "View Filter Manager");
        var button = (PushButton)panel.AddItem(new PushButtonData("TPT.Standalone.ViewFilterManager",
            "View Filter\nManager", typeof(Application).Assembly.Location, typeof(Command).FullName));
        button.AvailabilityClassName = typeof(ProjectAvailability).FullName;
        button.ToolTip = "View Filter Manager " + typeof(Application).Assembly.GetName().Version!.ToString(3) +
                         " — copy, order, edit, rename and transfer view filters.";
        var content = Path.Combine(Installation.Root, "Content");
        button.LargeImage = LoadIcon(Path.Combine(content, "icon32.png"));
        button.Image = LoadIcon(Path.Combine(content, "icon16.png"));
        return Result.Succeeded;
    }
    public Result OnShutdown(UIControlledApplication app) => Result.Succeeded;

    private static BitmapImage LoadIcon(string path)
    {
        var image = new BitmapImage(); image.BeginInit();
        image.CacheOption = BitmapCacheOption.OnLoad; image.UriSource = new Uri(path);
        image.EndInit(); image.Freeze(); return image;
    }
}

public sealed class ProjectAvailability : IExternalCommandAvailability
{
    public bool IsCommandAvailable(UIApplication app, CategorySet categories) =>
        app.Application.VersionNumber == "2026" && app.ActiveUIDocument?.Document is { IsFamilyDocument: false };
}

[Transaction(TransactionMode.Manual)]
[Regeneration(RegenerationOption.Manual)]
public sealed class Command : IExternalCommand
{
    private static RuntimeLoadContext? context;
    private static MethodInfo? run;
    public Result Execute(ExternalCommandData data, ref string message, ElementSet elements)
    {
        if (data.Application.ActiveUIDocument?.Document is not { IsFamilyDocument: false })
        { TaskDialog.Show("View Filter Manager", "Open a Revit project first."); return Result.Cancelled; }
        try
        {
            var folder = Installation.Root;
            if (run is null)
            {
                context = new RuntimeLoadContext(Path.Combine(folder, "ViewFilterManager.Runtime.dll"));
                var assembly = context.LoadFromAssemblyPath(Path.Combine(folder, "ViewFilterManager.Runtime.dll"));
                run = assembly.GetType("ViewFilterManager.Runtime.Entry", true)!.GetMethod("Run")!;
            }
            run.Invoke(null, [data.Application, Path.Combine(folder, "Content")]);
            return Result.Succeeded;
        }
        catch (Exception exception)
        {
            var error = exception is TargetInvocationException && exception.InnerException is not null ? exception.InnerException : exception;
            var log = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TPT", "ViewFilterManager", "Logs");
            try { Directory.CreateDirectory(log); File.WriteAllText(Path.Combine(log, "last-error.txt"), error.ToString()); } catch { }
            message = error.Message;
            TaskDialog.Show("View Filter Manager", "Unable to open the manager.\n\n" + error.Message + "\n\nDetails: " + Path.Combine(log, "last-error.txt"));
            return Result.Failed;
        }
    }
}

// Keep the complete runtime beside its startup DLL. Legacy pointer installs
// remain readable, but new installers use the colocated path exclusively.
internal static class Installation
{
    public static string Root
    {
        get
        {
            var bootstrap = Path.GetDirectoryName(typeof(Installation).Assembly.Location)!;
            var localRuntime = Path.Combine(bootstrap, "ViewFilterManager.Runtime.dll");
            if (File.Exists(localRuntime)) return bootstrap;
            var pointer = Path.Combine(bootstrap, "runtime-location.txt");
            var root = File.Exists(pointer) ? Path.GetFullPath(File.ReadAllText(pointer).Trim()) : bootstrap;
            var runtime = Path.Combine(root, "ViewFilterManager.Runtime.dll");
            try { using var stream = File.OpenRead(runtime); }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
                throw new IOException("Unable to read the View Filter Manager runtime at " + runtime +
                    ". Run the current installer with Revit closed to repair the installation.", error);
            }
            return root;
        }
    }
}

// Keep scripting dependencies private so other add-ins can use different versions.
internal sealed class RuntimeLoadContext(string mainAssembly) : AssemblyLoadContext("TPT.ViewFilterManager", false)
{
    private readonly AssemblyDependencyResolver resolver = new(mainAssembly);
    protected override Assembly? Load(AssemblyName name)
    {
        if (name.Name is "RevitAPI" or "RevitAPIUI" || name.Name!.StartsWith("System.") ||
            name.Name.StartsWith("Presentation") || name.Name is "WindowsBase" or "Microsoft.CSharp" or "netstandard")
            return null;
        var path = resolver.ResolveAssemblyToPath(name);
        return path is null ? null : LoadFromAssemblyPath(path);
    }
}
