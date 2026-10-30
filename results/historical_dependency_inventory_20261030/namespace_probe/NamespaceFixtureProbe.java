import org.jdom2.Element;
import org.jdom2.Namespace;

public final class NamespaceFixtureProbe {
    public static void main(String[] args) {
        Namespace own = Namespace.getNamespace("dup", "http://own.example.com");
        Namespace different = Namespace.getNamespace("dup", "http://other.example.com");
        Element invalid = new Element("root", own);
        String sameElement;
        try {
            invalid.addNamespaceDeclaration(different);
            sameElement = "accepted";
        } catch (RuntimeException exception) {
            sameElement = exception.getClass().getSimpleName();
        }
        Element distinctPrefix = new Element("root", own);
        distinctPrefix.addNamespaceDeclaration(Namespace.getNamespace("other", "http://other.example.com"));
        Element child = new Element("child", own);
        Element parent = new Element("parent", different);
        parent.addContent(child);
        System.out.println("{\"same_element_same_prefix_different_uri\":\"" + sameElement
            + "\",\"same_element_distinct_prefix_accepted\":true"
            + ",\"parent_child_same_prefix_accepted\":true"
            + ",\"child_own_namespace_visible\":" + child.getNamespacesInScope().contains(own)
            + ",\"parent_shadowed_namespace_visible\":" + child.getNamespacesInScope().contains(different) + "}");
    }
}
