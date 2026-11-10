import java.util.List;
import java.util.function.Consumer;
import java.util.function.Supplier;
import org.jdom2.Attribute;
import org.jdom2.Element;
import org.jdom2.IllegalAddException;
import org.jdom2.IllegalNameException;
import org.jdom2.Namespace;

/** Handwritten diagnostic for separating fixture legality from focal assertions. */
public final class NamespaceStageProbe {
    private static final Namespace P = Namespace.getNamespace("p", "urn:own");
    private static final Namespace Q = Namespace.getNamespace("q", "urn:declaration");
    private static final Namespace R = Namespace.getNamespace("r", "urn:attribute");

    private static void check(String id, String expected, Supplier<Element> setup,
            Consumer<List<Namespace>> oracle) {
        String result = "passed";
        boolean focalCalled = false;
        Element fixture = null;
        try {
            fixture = setup.get();
        } catch (IllegalAddException | IllegalNameException e) {
            result = e.getClass().getSimpleName();
        }
        if (fixture != null) {
            focalCalled = true;
            List<Namespace> actual = fixture.getNamespacesInScope();
            try {
                oracle.accept(actual);
            } catch (AssertionError e) {
                result = "assertion_failed";
            }
        }
        if (!expected.equals(result)) {
            throw new AssertionError(id + " expected " + expected + " but got " + result);
        }
        System.out.printf("%s\t%s\t%b%n", id, result, focalCalled);
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError();
        }
    }

    private static Element withDeclaration(Namespace ns) {
        Element element = new Element("e", P);
        element.addNamespaceDeclaration(ns);
        return element;
    }

    private static Element withAttribute(Namespace ns) {
        Element element = withDeclaration(Q);
        element.setAttribute(new Attribute("a", "value", ns));
        return element;
    }

    public static void main(String[] args) {
        System.out.println("case\tstatus\tfocal_called");
        check("same_element_prefix_collision", "IllegalAddException",
                () -> withDeclaration(Namespace.getNamespace("p", "urn:other")), actual -> {});
        check("declaration_attribute_collision", "IllegalAddException",
                () -> withAttribute(Namespace.getNamespace("q", "urn:attribute")), actual -> {});
        check("reserved_xml_rebind", "IllegalNameException",
                () -> new Element("e", Namespace.getNamespace("xml", "urn:other")), actual -> {});
        check("declaration_coexistence", "passed", () -> withDeclaration(Q), actual -> {
            require(actual.contains(P) && actual.contains(Q));
        });
        check("attribute_coexistence", "passed", () -> withAttribute(R), actual -> {
            require(actual.contains(Q) && actual.contains(R));
        });
        check("child_shadows_parent", "passed", () -> {
            Element parent = new Element("parent", Namespace.getNamespace("p", "urn:other"));
            Element child = new Element("child", P);
            parent.addContent(child);
            return child;
        }, actual -> {
            require(actual.contains(P) && !actual.contains(Namespace.getNamespace("p", "urn:other")));
        });
        check("unqualified_root_old_size_oracle", "assertion_failed", () -> new Element("root"),
                actual -> require(actual.size() == 3));
        check("unqualified_root_source_oracle", "passed", () -> new Element("root"), actual -> {
            require(actual.size() == 2 && actual.get(0).equals(Namespace.NO_NAMESPACE)
                    && actual.contains(Namespace.XML_NAMESPACE));
        });
    }
}
